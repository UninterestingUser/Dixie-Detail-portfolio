"""Quote requests with and without photos, the photo checks, the cleanup,
the control app's photo view, test records and the smoke test."""

import datetime
import hashlib
import hmac
import io
import json
import os
import time
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from appointments.models import Appointment
from control.fixtures import TailnetClient
from customers.models import Address, Consent, Customer
from publicapi import cleanup, photos
from publicapi.models import QuotePhoto, QuoteRequest, SmokeTestPass, TimeRequest, UploadSession

from .testing import BASE, CLEVELAND, CONSENTS, GOOD_TOKEN, KNOXVILLE, ApiTestCase, PublicClient, eastern, gps_exif, jpeg, open_day


def upload_file(content, name="photo.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class QuoteRequestTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.place_token = self.place()["place"]

    def session(self):
        response = self.client.post_json("quote-requests/uploads", {"turnstile": GOOD_TOKEN})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["session"]

    def upload(self, session, content, name="photo.jpg", content_type="image/jpeg", expect=201):
        response = self.client.post(f"{BASE}quote-requests/uploads/{session}/photos", {"photo": upload_file(content, name, content_type)})
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def body(self, **changes):
        body = {
            "vehicle": {"year": 2021, "make": "Ford", "model": "Transit 250"},
            "service": self.full_detail.pk,
            "description": "Work van, very dirty inside.\nSeats need shampoo.",
            "place": self.place_token,
            "first_name": "Morgan",
            "last_name": "Fleet",
            "mobile": "423-555-0160",
            "consents": dict(CONSENTS),
            "preferred_days": "Weekday mornings",
            "turnstile": GOOD_TOKEN,
        }
        body.update(changes)
        return {key: value for key, value in body.items() if value is not None}

    def send(self, expect=201, **changes):
        response = self.client.post_json("quote-requests", self.body(**changes))
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def stored(self, photo_id):
        photo = QuotePhoto.objects.get(public_id=photo_id)
        return photo, photos.path_of(photo.file_name)


class QuoteRequestTests(QuoteRequestTestCase):
    def test_a_request_without_photos(self):
        answer = self.send()
        self.assertEqual(answer["photos"], 0)
        self.assertIn("reply with a price", answer["message"])
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertEqual(request.vehicle_class, self.vans)
        self.assertEqual(request.vehicle_text, "2021 Ford Transit 250")
        self.assertEqual(request.service, self.full_detail)
        self.assertEqual(request.description, "Work van, very dirty inside.\nSeats need shampoo.")
        self.assertEqual(request.preferred_days, "Weekday mornings")
        self.assertEqual(request.status, QuoteRequest.Status.NEW)
        self.assertEqual(request.service_address.city, "Cleveland")
        self.assertEqual(request.customer.mobile, "4235550160")
        self.assertEqual(Consent.objects.filter(customer=request.customer).count(), 1)
        # Not an appointment, and no time is held.
        self.assertFalse(Appointment.objects.exists())

    def test_an_add_on_must_go_with_the_service(self):
        """Decision 0106: the same rule as a quote."""
        refused = self.send(expect=400, service=self.exterior.pk, add_ons=[self.seats.pk])
        self.assertEqual((refused["field"], refused["message"]), ("add_ons", "Seat Extraction can't be added to Exterior Only."))
        self.assertEqual(self.send(expect=400, service="not_sure", add_ons=[self.seats.pk])["field"], "add_ons")
        self.assertFalse(QuoteRequest.objects.exists())

    def test_not_sure_and_the_photo_card(self):
        answer = self.send(vehicle={"photo_card": self.vans.pk, "year": 1978, "make": "Dodge", "model": "Tradesman"}, service="not_sure")
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertIsNone(request.service)
        self.assertTrue(request.photo_card)
        self.assertEqual(request.vehicle_text, "1978 Dodge Tradesman (Full-size Vans photo card)")

    def test_a_description_is_required(self):
        self.assertEqual(self.send(expect=400, description="   ")["field"], "description")
        self.assertEqual(self.send(expect=400, description="x" * 2001)["field"], "description")

    def test_a_vehicle_booked_online_is_sent_to_booking(self):
        answer = self.send(expect=422, vehicle={"year": 2019, "make": "Toyota", "model": "RAV4"})
        self.assertEqual(answer["error"], "book_online")
        self.assertFalse(QuoteRequest.objects.exists())

    def test_a_class_the_owner_sets_to_quote_uses_the_same_path(self):
        self.medium.booking = "quote"
        self.medium.save()
        lookup = self.client.get_api("vehicles/lookup", {"year": 2019, "make": "Toyota", "model": "RAV4"}).json()
        self.assertTrue(lookup["booked_by_quote"])
        self.assertEqual(self.quote(expect=422)["error"], "ask_for_quote")
        answer = self.send(vehicle={"year": 2019, "make": "Toyota", "model": "RAV4"})
        self.assertEqual(QuoteRequest.objects.get(reference=answer["reference"]).vehicle_class, self.medium)

    def test_turnstile(self):
        self.assertEqual(self.send(expect=403, turnstile="refused")["error"], "turnstile_failed")
        response = self.client.post_json("quote-requests/uploads", {"turnstile": "refused"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(UploadSession.objects.exists())

    def test_a_request_with_photos(self):
        session = self.session()
        first = self.upload(session, jpeg())
        second = self.upload(session, jpeg(color="red"))
        dropped = self.upload(session, jpeg(color="green"))
        answer = self.send(session=session, photos=[first["photo"], second["photo"]])
        self.assertEqual(answer["photos"], 2)
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertEqual(request.photos.count(), 2)
        # A photo picked but left out of the request goes at once.
        self.assertFalse(QuotePhoto.objects.filter(public_id=dropped["photo"]).exists())
        self.assertEqual(len(os.listdir(self.photo_dir)), 2)
        # The session can't be used again.
        self.upload(session, jpeg(), expect=409)

    def test_a_photo_can_be_removed_before_sending(self):
        session = self.session()
        photo = self.upload(session, jpeg())
        response = self.client.delete(f"{BASE}quote-requests/uploads/{session}/photos/{photo['photo']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(os.listdir(self.photo_dir), [])

    def test_photos_from_another_session_are_refused(self):
        mine, theirs = self.session(), self.session()
        photo = self.upload(theirs, jpeg())
        self.assertEqual(self.send(expect=400, session=mine, photos=[photo["photo"]])["field"], "photos")


class PhotoTests(QuoteRequestTestCase):
    def test_no_location_or_other_metadata_survives(self):
        original = jpeg((4000, 3000), exif=gps_exif())
        self.assertIn(b"MadeUpCameraCo", original)
        session = self.session()
        uploaded = self.upload(session, original)
        photo, path = self.stored(uploaded["photo"])
        saved = path.read_bytes()
        self.assertNotIn(b"MadeUpCameraCo", saved)
        self.assertNotIn(b"Exif", saved)
        with Image.open(path) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(dict(image.getexif()), {})
            self.assertNotIn("exif", image.info)
            self.assertNotIn("icc_profile", image.info)
            self.assertEqual(image.size, (2560, 1920))
        self.assertEqual((photo.width, photo.height), (2560, 1920))
        # Saved under a random name, readable by the app only.
        self.assertRegex(path.name, r"^[0-9a-f]{32}\.jpg$")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_a_heic_photo_from_an_iphone(self):
        out = io.BytesIO()
        Image.new("RGB", (1200, 900), "teal").save(out, "HEIF", exif=gps_exif().tobytes())
        heic = out.getvalue()
        self.assertIn(b"ftypheic", heic[:32])
        uploaded = self.upload(self.session(), heic, "IMG_0001.HEIC", "image/heic")
        _, path = self.stored(uploaded["photo"])
        with Image.open(path) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1200, 900))
            self.assertEqual(dict(image.getexif()), {})
        self.assertNotIn(b"MadeUpCameraCo", path.read_bytes())

    def test_png_and_webp(self):
        session = self.session()
        self.upload(session, jpeg(mode="RGBA", color=(0, 0, 255, 128), image_format="PNG"), "photo.png", "image/png")
        self.upload(session, jpeg(image_format="WEBP"), "photo.webp", "image/webp")

    def test_a_file_that_is_not_an_image(self):
        session = self.session()
        answer = self.upload(session, b"%PDF-1.7 not a photo at all", "photo.jpg", "image/jpeg", expect=422)
        self.assertEqual(answer["error"], "not_an_image")
        gif = io.BytesIO()
        Image.new("RGB", (10, 10)).save(gif, "GIF")
        self.assertEqual(self.upload(session, gif.getvalue(), "photo.gif", "image/gif", expect=422)["error"], "not_an_image")
        self.assertEqual(os.listdir(self.photo_dir), [])

    def test_a_multi_picture_jpeg_keeps_its_first_picture(self):
        # Some Android phones and cameras save a JPEG with a second picture in
        # it; Pillow opens it as MPO. The first picture is the photo.
        out = io.BytesIO()
        Image.new("RGB", (64, 48), (200, 0, 0)).save(out, "MPO", save_all=True, append_images=[Image.new("RGB", (64, 48), (0, 0, 200))])
        uploaded = self.upload(self.session(), out.getvalue(), "photo.jpg", "image/jpeg")
        _, path = self.stored(uploaded["photo"])
        with Image.open(path) as image:
            self.assertEqual(image.format, "JPEG")
            red, green, blue = image.convert("RGB").getpixel((32, 24))
            self.assertGreater(red, 150)
            self.assertLess(blue, 60)

    def test_other_formats_never_reach_their_decoders(self):
        # Decision 0120: Image.open tries only the four accepted formats, so a
        # file in any other format is refused before its decoder reads it.
        # Checked in this process, where the mock applies; the upload path
        # runs the same code in the photo worker's own process.
        from PIL import TiffImagePlugin

        from photoworker import imaging

        session = self.session()
        for kind in ("TIFF", "GIF", "BMP", "PDF"):
            out = io.BytesIO()
            Image.new("RGB", (10, 10)).save(out, kind)
            with self.subTest(kind), mock.patch.object(TiffImagePlugin.TiffImageFile, "_open", side_effect=AssertionError("TIFF decoder reached")) as tiff:
                with self.assertRaises(imaging.Refused):
                    imaging.clean(out.getvalue())
                tiff.assert_not_called()
            answer = self.upload(session, out.getvalue(), "photo.jpg", "image/jpeg", expect=422)
            self.assertEqual(answer["error"], "not_an_image")
        self.assertEqual(photos.FORMATS, ("JPEG", "PNG", "WEBP", "HEIF"))
        self.assertEqual(os.listdir(self.photo_dir), [])

    def test_an_absurd_pixel_count(self):
        out = io.BytesIO()
        Image.new("1", (9000, 9000)).save(out, "PNG")
        answer = self.upload(self.session(), out.getvalue(), "huge.png", "image/png", expect=422)
        self.assertEqual(answer["error"], "not_an_image")

    def test_a_photo_too_large(self):
        with override_settings(QUOTE_REQUEST_PHOTO_MAX_MB=1):
            answer = self.upload(self.session(), b"\xff\xd8" + os.urandom(1_200_000), expect=413)
        self.assertEqual(answer["error"], "photo_too_large")

    def test_one_photo_too_many(self):
        session = self.session()
        with override_settings(QUOTE_REQUEST_MAX_PHOTOS=2):
            ids = [self.upload(session, jpeg())["photo"] for _ in range(2)]
            self.assertEqual(self.upload(session, jpeg(), expect=422)["error"], "too_many_photos")
            self.assertEqual(self.send(expect=422, session=session, photos=[*ids, "another-photo-id"])["error"], "too_many_photos")

    def test_no_public_endpoint_returns_a_photo(self):
        session = self.session()
        uploaded = self.upload(session, jpeg())
        photo, _ = self.stored(uploaded["photo"])
        self.assertNotIn(photo.file_name, json.dumps(uploaded))
        answer = self.send(session=session, photos=[uploaded["photo"]])
        self.assertNotIn(photo.file_name, json.dumps(answer))
        self.assertEqual(self.client.get(f"/requests/photos/{photo.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}quote-requests/uploads/{session}/photos/{uploaded['photo']}").status_code, 405)


class ControlAppTests(QuoteRequestTestCase):
    def test_the_owner_sees_the_request_and_its_photos_over_the_tailnet(self):
        session = self.session()
        uploaded = self.upload(session, jpeg())
        answer = self.send(session=session, photos=[uploaded["photo"]])
        request = QuoteRequest.objects.get(reference=answer["reference"])
        photo = request.photos.get()
        owner = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        tailnet = TailnetClient()
        self.assertEqual(tailnet.get(f"/requests/photos/{photo.pk}/").status_code, 302)
        tailnet.force_login(owner)
        listing = tailnet.get("/requests/")
        self.assertContains(listing, "Morgan Fleet")
        page = tailnet.get(f"/requests/quotes/{request.pk}/")
        self.assertContains(page, "Work van, very dirty inside.")
        self.assertContains(page, f"/requests/photos/{photo.pk}/")
        shown = tailnet.get(f"/requests/photos/{photo.pk}/")
        self.assertEqual(shown.status_code, 200)
        self.assertEqual(shown["Content-Type"], "image/jpeg")
        self.assertTrue(b"".join(shown.streaming_content).startswith(b"\xff\xd8"))
        schedule = tailnet.get("/schedule/")
        self.assertContains(schedule, "Quote request: Morgan Fleet")


class CleanupTests(QuoteRequestTestCase):
    def test_photos_never_attached_go_after_a_day(self):
        session = self.session()
        kept = self.upload(session, jpeg())
        old = self.upload(self.session(), jpeg())
        QuotePhoto.objects.filter(public_id=old["photo"]).update(uploaded_at=timezone.now() - datetime.timedelta(hours=25))
        self.send(session=session, photos=[kept["photo"]])
        cleaned = cleanup.run()
        self.assertEqual(cleaned.unattached_photos, 1)
        self.assertEqual(QuotePhoto.objects.count(), 1)
        self.assertEqual(len(os.listdir(self.photo_dir)), 1)

    def test_a_closed_requests_photos_go_after_the_set_days_and_the_description_stays(self):
        session = self.session()
        uploaded = self.upload(session, jpeg())
        request = QuoteRequest.objects.get(reference=self.send(session=session, photos=[uploaded["photo"]])["reference"])
        request.status = QuoteRequest.Status.DECLINED
        request.closed_at = timezone.now() - datetime.timedelta(days=89)
        request.save()
        self.assertEqual(cleanup.run().closed_request_photos, 0)
        QuoteRequest.objects.filter(pk=request.pk).update(closed_at=timezone.now() - datetime.timedelta(days=91))
        self.assertEqual(cleanup.run().closed_request_photos, 1)
        request.refresh_from_db()
        self.assertEqual(request.photos.count(), 0)
        self.assertEqual(request.photos_deleted_count, 1)
        self.assertIsNotNone(request.photos_deleted_at)
        self.assertEqual(request.description, "Work van, very dirty inside.\nSeats need shampoo.")
        self.assertEqual(os.listdir(self.photo_dir), [])

    def test_a_job_done_or_canceled_closes_the_request(self):
        from appointments import booking

        session = self.session()
        uploaded = self.upload(session, jpeg())
        request = QuoteRequest.objects.get(reference=self.send(session=session, photos=[uploaded["photo"]])["reference"])
        job = booking.book(request.customer, None, eastern(open_day(3), 8), booking.JobInputs(self.exterior, self.medium, None, 1), address=request.service_address)
        request.appointment = job
        request.status = QuoteRequest.Status.BOOKED
        request.save()
        self.assertEqual(cleanup.run().closed_request_photos, 0)
        Appointment.objects.filter(pk=job.pk).update(status=Appointment.Status.CANCELED, canceled_at=timezone.now() - datetime.timedelta(days=100))
        self.assertEqual(cleanup.run().closed_request_photos, 1)

    def test_stray_files_go(self):
        stray = photos.folder() / f"{'0' * 32}.part"
        stray.write_bytes(b"half")
        os.utime(stray, (time.time() - 90_000, time.time() - 90_000))
        self.assertEqual(cleanup.run().stray_files, 1)
        self.assertFalse(stray.exists())


class TestRecordTests(QuoteRequestTestCase):
    def test_delete_test_records_removes_test_customers_and_everything_of_theirs(self):
        real = Customer.objects.create(first_name="Real", mobile="4235550111")
        session = self.session()
        uploaded = self.upload(session, jpeg())
        self.send(session=session, photos=[uploaded["photo"]], mobile="4235550199")
        quote = self.quote(place=self.place_token)
        self.client.post_json("bookings", self.booking_body(quote, eastern(open_day(3), 8), mobile="4235550199"))
        # The booking matched the request's test customer quietly.
        self.assertEqual(Customer.objects.filter(is_test=True).count(), 1)
        self.assertTrue(Appointment.objects.get().is_test)
        output = io.StringIO()
        call_command("delete_test_records", stdout=output)
        self.assertIn("Deleted 1 test customer(s), 1 appointment(s), 1 quote request(s) with 1 photo(s)", output.getvalue())
        self.assertEqual(list(Customer.objects.all()), [real])
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(QuoteRequest.objects.exists())
        self.assertFalse(Address.objects.exists())
        self.assertEqual(os.listdir(self.photo_dir), [])

    def test_a_dry_run_changes_nothing(self):
        self.send(mobile="4235550199")
        output = io.StringIO()
        call_command("delete_test_records", "--dry-run", stdout=output)
        self.assertIn("Would delete: Deleted 1 test customer(s)", output.getvalue())
        self.assertTrue(QuoteRequest.objects.exists())


class SmokeTestTests(ApiTestCase):
    def test_the_smoke_test_books_and_requests_then_deletes_both(self):
        client = PublicClient(origin=None)

        def call(api, method, path, body=None, params=None, data=None, content_type="application/json"):
            url = BASE + path
            if method == "GET":
                response = client.get(url, params or {})
            elif body is not None:
                response = client.post(url, json.dumps(body), content_type="application/json")
            else:
                response = client.generic(method, url, data, content_type=content_type)
            return response.status_code, response.json()

        output = io.StringIO()
        with mock.patch("publicapi.management.commands.api_smoke_test.Api.call", call):
            call_command("api_smoke_test", place_id=CLEVELAND, stdout=output)
        text = output.getvalue()
        self.assertIn("api-smoke-test: booked", text)
        self.assertIn("api-smoke-test: quote request", text)
        # The quote request matched the booking's test customer.
        self.assertIn("Deleted 1 test customer(s), 1 appointment(s), 1 quote request(s) with 1 photo(s)", text)
        self.assertTrue(text.strip().endswith("api-smoke-test: PASS"))
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(SmokeTestPass.objects.exists())
        self.assertEqual(os.listdir(self.photo_dir), [])
        self.siteverify.assert_not_called()

    def test_a_smoke_test_pass_works_only_from_the_database(self):
        self.assertEqual(self.client.post_json("quote-requests/uploads", {"turnstile": "smoke-test:made-up"}).status_code, 403)


def signed(body, key="made-up-offline-signing-key-for-tests", stamp=None):
    raw = json.dumps(body).encode()
    stamp = str(int(stamp or time.time()))
    signature = hmac.new(key.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, {"X-Dixie-Timestamp": stamp, "X-Dixie-Signature": signature}


class TimeRequestTests(ApiTestCase):
    def body(self, **changes):
        body = {
            "request_id": str(uuid.uuid4()),
            "submitted_at": eastern(open_day(-1), 21).isoformat(),
            "vehicle": {"year": 2019, "make": "Toyota", "model": "RAV4"},
            "condition": 2,
            "service": self.full_detail.pk,
            "add_ons": [self.seats.pk],
            "place_id": CLEVELAND,
            "preferred_start": eastern(open_day(4), 8).isoformat(),
            "first_name": "Avery",
            "mobile": "4235550123",
            "payment_method": "card",
            "consents": dict(CONSENTS),
            "shown": {"total": "355.00", "pricebook_version": 1},
        }
        body.update(changes)
        return body

    def send(self, body, expect=201, **sign):
        raw, headers = signed(body, **sign)
        client = PublicClient(origin=None, visitor="104.16.0.1")
        response = client.post(f"{BASE}time-requests", raw, content_type="application/json", headers=headers)
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_a_replayed_request_is_priced_on_arrival(self):
        body = self.body()
        self.send(body)
        request = TimeRequest.objects.get()
        self.assertEqual(request.quote.total_before_tax, 355)
        self.assertFalse(request.price_differs)
        self.assertEqual(request.problem, "")
        self.assertEqual(request.service_address.city, "Cleveland")
        self.assertEqual(request.inputs["service"], "Full Detail")
        self.assertEqual(request.customer.first_name, "Avery")
        self.assertEqual(Consent.objects.get(customer=request.customer, kind="appointment").recorded_at, datetime.datetime.fromisoformat(body["submitted_at"]))
        # A request is not an appointment.
        self.assertFalse(Appointment.objects.exists())
        # A second replay of the same request changes nothing.
        self.assertTrue(self.send(body, expect=200)["duplicate"])
        self.assertEqual(TimeRequest.objects.count(), 1)

    def test_a_different_price_is_flagged_for_the_owner(self):
        self.send(self.body(shown={"total": "330.00", "pricebook_version": 1}))
        request = TimeRequest.objects.get()
        self.assertTrue(request.price_differs)
        owner = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        tailnet = TailnetClient()
        tailnet.force_login(owner)
        self.assertContains(tailnet.get("/schedule/"), "Offline request: Avery")
        self.assertContains(tailnet.get("/schedule/"), "price differs")
        self.assertContains(tailnet.get(f"/requests/offline/{request.pk}/"), "differs from the $330.00 the customer saw")

    def test_an_address_outside_the_area_is_kept_with_the_problem(self):
        self.send(self.body(place_id=KNOXVILLE))
        request = TimeRequest.objects.get()
        self.assertIsNone(request.quote)
        self.assertIn("outside the area", request.problem)

    def test_unsigned_or_stale_requests_are_refused(self):
        body = self.body()
        self.send(body, expect=401, key="a-wrong-key")
        self.send(body, expect=401, stamp=time.time() - 600)
        client = PublicClient(origin=None)
        self.assertEqual(client.post_json("time-requests", body).status_code, 401)
        with override_settings(OFFLINE_REQUESTS_SIGNING_KEY=""):
            self.send(body, expect=401, key="")
        self.assertFalse(TimeRequest.objects.exists())
