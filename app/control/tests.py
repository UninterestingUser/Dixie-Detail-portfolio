import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from billing.methods import PaymentMethod
from billing.models import Payment
from control.context_processors import brand_colors
from control.search import find_customers, phone_digits
from customers.models import Address, Customer, SecondContact
from dixie.settings_base import trusted_origins
from vehicles.models import SizeVariant, Vehicle, VehicleClass

# Every control app request comes in through the private door over Tailscale,
# which Caddy marks with this header (core/middleware.py).
TAILNET = {"X-Dixie-Entrance": "tailnet"}
# An invented tailnet address for the HTTPS sign-in tests.
TAILNET_HOST = "control.example-tailnet.ts.net"


class TailnetClient(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, headers={**TAILNET, **kwargs.pop("headers", {})}, **kwargs)


class ControlTestCase(TestCase):
    client_class = TailnetClient

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        # Invented customers.
        cls.pat = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101", email="pat@example.com")
        cls.lee = Customer.objects.create(first_name="Lee", last_name="Sample", company="Sample Farms", mobile="4235550102")
        cls.sam = Customer.objects.create(first_name="Sam", last_name="Nophone")
        SecondContact.objects.create(customer=cls.pat, name="Jordan Partner", phone="4235550199", relationship="spouse")
        cls.address = Address.objects.create(customer=cls.pat, line1="100 Sample Rd", city="Calhoun", state="TN", zip_code="37309")
        cls.vehicle_class = VehicleClass.objects.create(name="Coupes & Sedans", size_variant_measures="doors")
        cls.four_doors = SizeVariant.objects.create(vehicle_class=cls.vehicle_class, value=4, label="four doors")
        cls.other_class = VehicleClass.objects.create(name="Midsize SUVs", size_variant_measures="seat rows")
        cls.silver = Vehicle.objects.create(customer=cls.pat, year=2019, make="Honda", model="Accord", color="silver",
                                            vehicle_class=cls.vehicle_class, size_variant=cls.four_doors)
        cls.blue = Vehicle.objects.create(customer=cls.pat, year=2019, make="Honda", model="Accord", color="dark blue")
        cls.appointment = Appointment.objects.create(
            customer=cls.pat, vehicle=cls.silver, service_address=cls.address, source=Appointment.Source.OWNER,
            scheduled_start=datetime.datetime(2026, 10, 21, 15, 30, tzinfo=datetime.UTC), status=Appointment.Status.COMPLETED,
        )
        AppointmentLine.objects.create(appointment=cls.appointment, kind=AppointmentLine.Kind.CUSTOM,
                                       description="Invented detail", amount=Decimal("290.00"))
        Payment.objects.create(appointment=cls.appointment, method=PaymentMethod.CASH, split_method=PaymentMethod.VENMO,
                               amount=Decimal("290.00"), tip=Decimal("20.00"), paid_at=timezone.now())

    def setUp(self):
        self.client.force_login(self.user)


class SearchTests(ControlTestCase):
    def names(self, query):
        return [str(customer) for customer in find_customers(query)[0]]

    def test_phone_in_any_format(self):
        for query in ("(423) 555-0101", "423-555-0101", "423.555.0101", "4235550101", "+1 423 555 0101", "1-423-555-0101"):
            with self.subTest(query=query):
                self.assertEqual(self.names(query), ["Pat Example"])

    def test_part_of_a_phone_number(self):
        self.assertEqual(self.names("0102"), ["Lee Sample"])
        self.assertEqual(self.names("555-01"), ["Pat Example", "Lee Sample"])

    def test_a_second_contacts_number_finds_the_customer(self):
        self.assertEqual(self.names("(423) 555-0199"), ["Pat Example"])

    def test_by_name(self):
        self.assertEqual(self.names("pat"), ["Pat Example"])
        self.assertEqual(self.names("Pat Example"), ["Pat Example"])
        self.assertEqual(self.names("example pat"), ["Pat Example"])
        self.assertEqual(self.names("Sample Farms"), ["Lee Sample"])
        self.assertEqual(self.names("Jordan"), ["Pat Example"])
        self.assertEqual(self.names("Pat Sample"), [])

    def test_name_and_part_of_a_number(self):
        self.assertEqual(self.names("Pat 0101"), ["Pat Example"])
        self.assertEqual(self.names("Pat 0102"), [])

    def test_too_little_to_search(self):
        self.assertEqual(self.names(""), [])
        self.assertEqual(self.names("42"), [])

    def test_phone_digits(self):
        self.assertEqual(phone_digits("+1 (423) 555-0101"), "4235550101")
        self.assertEqual(phone_digits("555-0101"), "5550101")

    def test_the_search_page_and_its_htmx_results(self):
        page = self.client.get(reverse("customers"), {"q": "423 555 0101"})
        self.assertContains(page, "Pat Example")
        self.assertContains(page, "<html", html=False)
        self.assertNotContains(page, "Lee Sample")
        results = self.client.get(reverse("customers"), {"q": "lee"}, headers={"HX-Request": "true"})
        self.assertContains(results, "Lee Sample")
        self.assertNotContains(results, "<html", html=False)
        self.assertIn("HX-Request", results["Vary"])

    def test_results_show_vehicles_with_their_color(self):
        results = self.client.get(reverse("customers"), {"q": "Pat"}, headers={"HX-Request": "true"})
        self.assertContains(results, "2019 Honda Accord, silver")
        self.assertContains(results, "2019 Honda Accord, dark blue")

    def test_no_match(self):
        self.assertContains(self.client.get(reverse("customers"), {"q": "Nobody"}), "No customer matches")


class ScreenTests(ControlTestCase):
    def test_every_screen_loads(self):
        for name, args in (
            ("customers", []),
            ("customer", [self.pat.pk]),
            ("customer", [self.sam.pk]),
            ("customer-new", []),
            ("customer-edit", [self.pat.pk]),
            ("vehicle-new", [self.pat.pk]),
            ("vehicle-edit", [self.silver.pk]),
            ("account", []),
            ("offline", []),
            ("manifest", []),
            ("service-worker", []),
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        self.assertRedirects(self.client.get("/"), reverse("schedule"))

    def test_the_customer_page(self):
        page = self.client.get(reverse("customer", args=[self.pat.pk]))
        for text in (
            "(423) 555-0101", "pat@example.com", "Jordan Partner", "(423) 555-0199", "100 Sample Rd",
            "2019 Honda Accord, silver", "2019 Honda Accord, dark blue", "To fill in: vehicle class",
            "Wed, Oct 21, 2026, 11:30 AM", "Invented detail", "$290.00", "Paid $290.00 by Cash and Venmo, tip $20.00",
            "Paid in full",
        ):
            with self.subTest(text=text):
                self.assertContains(page, text)

    def test_an_unpaid_completed_job_says_so(self):
        Payment.objects.all().delete()
        self.assertContains(self.client.get(reverse("customer", args=[self.pat.pk])), "Not paid")

    def test_a_vehicle_is_named_with_its_color(self):
        self.assertEqual(str(self.silver), "2019 Honda Accord, silver")
        self.assertEqual(str(Vehicle(make="Honda", model="Accord")), "Honda Accord")
        self.assertEqual(str(Vehicle(color="red")), "Vehicle, red")

    def test_brand_colors_come_from_business_yaml(self):
        colors = brand_colors()
        page = self.client.get(reverse("customers"))
        self.assertContains(page, f"--red: {colors['red']}")
        self.assertContains(page, f"--navy: {colors['navy']}")
        manifest = self.client.get(reverse("manifest")).json()
        self.assertEqual((manifest["theme_color"], manifest["display"], manifest["start_url"]), (colors["navy"], "standalone", "/"))
        self.assertEqual({icon["sizes"] for icon in manifest["icons"]}, {"192x192", "512x512"})
        for icon in manifest["icons"]:
            with self.subTest(icon=icon["src"]):
                response = self.client.get(icon["src"])
                self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/png"))

    def test_static_files_are_served(self):
        for path in ("/static/control/app.css", "/static/control/app.js", "/static/control/htmx-2.0.11.min.js"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


class EditTests(ControlTestCase):
    def test_add_a_customer_with_a_formatted_number(self):
        response = self.client.post(reverse("customer-new"), {"first_name": "Robin", "last_name": "Invented", "mobile": "+1 (423) 555-0177"})
        robin = Customer.objects.get(first_name="Robin")
        self.assertRedirects(response, reverse("customer", args=[robin.pk]))
        self.assertEqual(robin.mobile, "4235550177")
        self.assertEqual(robin.history.first().history_user, self.user)

    def test_a_bad_number_is_refused(self):
        response = self.client.post(reverse("customer-new"), {"first_name": "Robin", "mobile": "555-01"})
        self.assertContains(response, "Enter a 10-digit US phone number")
        self.assertFalse(Customer.objects.filter(first_name="Robin").exists())

    def test_edit_a_customer(self):
        form = self.client.get(reverse("customer-edit", args=[self.pat.pk]))
        self.assertContains(form, 'value="(423) 555-0101"')
        self.client.post(reverse("customer-edit", args=[self.pat.pk]), {"first_name": "Pat", "last_name": "Example", "mobile": "423 555 0101", "notes": "Gate code needed"})
        self.pat.refresh_from_db()
        self.assertEqual((self.pat.notes, self.pat.mobile, self.pat.email), ("Gate code needed", "4235550101", ""))

    def test_add_and_edit_a_vehicle(self):
        self.client.post(reverse("vehicle-new", args=[self.lee.pk]), {
            "year": "2021", "make": "Toyota", "model": "Camry", "color": "white",
            "vehicle_class": self.vehicle_class.pk, "size_variant": self.four_doors.pk,
        })
        camry = self.lee.vehicles.get()
        self.assertEqual(str(camry), "2021 Toyota Camry, white")
        self.client.post(reverse("vehicle-edit", args=[camry.pk]), {"year": "2021", "make": "Toyota", "model": "Camry", "color": "pearl white"})
        camry.refresh_from_db()
        self.assertEqual((camry.color, camry.vehicle_class), ("pearl white", None))

    def test_a_size_variant_of_another_class_is_refused(self):
        response = self.client.post(reverse("vehicle-new", args=[self.lee.pk]), {
            "make": "Toyota", "model": "Camry", "vehicle_class": self.other_class.pk, "size_variant": self.four_doors.pk,
        })
        self.assertContains(response, "Pick a size variant of the vehicle class above")
        self.assertFalse(self.lee.vehicles.exists())


class SignInTests(TestCase):
    client_class = TailnetClient

    def test_every_page_needs_sign_in(self):
        for path in (reverse("customers"), reverse("customer-new"), reverse("account"), "/"):
            with self.subTest(path=path):
                self.assertRedirects(self.client.get(path), f"{reverse('sign-in')}?next={path}", fetch_redirect_response=False)

    def test_install_pages_and_health_do_not(self):
        for path in (reverse("sign-in"), reverse("manifest"), reverse("service-worker"), reverse("offline"), "/health"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_the_public_door_still_serves_nothing_else(self):
        public = Client(headers={"X-Dixie-Entrance": "public"})
        for path in (reverse("sign-in"), reverse("customers"), "/static/control/app.css", reverse("manifest"), "/admin/"):
            with self.subTest(path=path):
                self.assertEqual(public.get(path).status_code, 404)

    def test_trusted_origins_leave_out_the_local_names(self):
        self.assertEqual(
            trusted_origins([TAILNET_HOST, "api.example.com", "127.0.0.1", "localhost"]),
            [f"https://{TAILNET_HOST}", "https://api.example.com"],
        )

    @override_settings(ALLOWED_HOSTS=[TAILNET_HOST, "localhost"], CSRF_TRUSTED_ORIGINS=trusted_origins([TAILNET_HOST]))
    def test_sign_in_over_https_behind_caddy(self):
        """As on the server: tailscale serve ends HTTPS, Caddy marks the request
        as HTTPS and as from the tailnet, and the browser sends its Origin."""
        get_user_model().objects.create_user("owner", password="an-invented-password-1")
        browser = Client(enforce_csrf_checks=True, headers={**TAILNET, "X-Forwarded-Proto": "https"}, HTTP_HOST=TAILNET_HOST)
        form = browser.get(reverse("sign-in"))
        self.assertTrue(form.cookies["csrftoken"]["secure"])
        token = form.context["csrf_token"]
        signed_in = browser.post(
            reverse("sign-in"),
            {"username": "owner", "password": "an-invented-password-1", "csrfmiddlewaretoken": token},
            headers={"Origin": f"https://{TAILNET_HOST}", "Referer": f"https://{TAILNET_HOST}/sign-in/"},
        )
        self.assertRedirects(signed_in, reverse("schedule"), fetch_redirect_response=False)
        self.assertTrue(signed_in.cookies["sessionid"]["secure"])
        self.assertTrue(signed_in.cookies["sessionid"]["httponly"])
        self.assertEqual(browser.get(reverse("customers")).status_code, 200)

    @override_settings(ALLOWED_HOSTS=[TAILNET_HOST], CSRF_TRUSTED_ORIGINS=trusted_origins([TAILNET_HOST]))
    def test_a_form_posted_from_another_site_is_refused(self):
        browser = Client(enforce_csrf_checks=True, headers={**TAILNET, "X-Forwarded-Proto": "https"}, HTTP_HOST=TAILNET_HOST)
        token = browser.get(reverse("sign-in")).context["csrf_token"]
        response = browser.post(
            reverse("sign-in"), {"username": "owner", "password": "x", "csrfmiddlewaretoken": token},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertEqual(response.status_code, 403)

    def test_sign_out(self):
        user = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        self.client.force_login(user)
        self.assertRedirects(self.client.post(reverse("sign-out")), reverse("sign-in"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("customers")).status_code, 302)


class AdminTests(TestCase):
    client_class = TailnetClient

    def test_the_admin_is_for_superusers_only(self):
        User = get_user_model()
        staff = User.objects.create_user("helper", password="an-invented-password-1", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        superuser = User.objects.create_superuser("owner", password="an-invented-password-1")
        self.client.force_login(superuser)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/customers/customer/").status_code, 200)
        self.assertEqual(self.client.get("/admin/vehicles/vehicle/").status_code, 200)
