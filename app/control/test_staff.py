import datetime

from django.urls import reverse
from django.utils import timezone

from appointments import booking
from pricebook.models import Service
from pricebook.pricing import price_job
from staff.authorization import CrewError, assign_crew, authorizable_services, staff_choices
from staff.models import Assignment, ServiceAuthorization

from .fixtures import JobsTestCase, local


class AuthorizationScreenTests(JobsTestCase):
    def toggle(self, member, service, on, page="staff"):
        data = {"from": page}
        if on:
            data["authorized"] = "on"
        return self.client.post(reverse("authorization", args=[member.pk, service.pk]), data)

    def test_the_screens_load(self):
        for name, args in (("staff", []), ("staff-member", [self.helper.pk]), ("staff-member", [self.owner.pk]),
                           ("services", []), ("service", [self.full_detail.pk])):
            with self.subTest(name=name, args=args):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_both_pages_edit_the_same_record(self):
        response = self.toggle(self.helper, self.full_detail, True, page="staff")
        self.assertContains(response, "checked")
        self.assertTrue(ServiceAuthorization.objects.filter(staff_member=self.helper, service=self.full_detail).exists())
        service_page = self.client.get(reverse("service", args=[self.full_detail.pk]))
        self.assertContains(service_page, f'id="auth-{self.helper.pk}-{self.full_detail.pk}" name="authorized" checked')
        self.toggle(self.helper, self.full_detail, False, page="service")
        self.assertFalse(ServiceAuthorization.objects.exists())
        staff_page = self.client.get(reverse("staff-member", args=[self.helper.pk]))
        self.assertNotContains(staff_page, f'id="auth-{self.helper.pk}-{self.full_detail.pk}" name="authorized" checked')
        # Who changed it is kept.
        self.assertEqual(ServiceAuthorization.history.filter(history_type="+").get().history_user, self.owner_user)

    def test_managers_are_authorized_for_every_service_including_new_ones(self):
        new = Service.objects.create(name="Invented Ceramic Coating", kind=Service.Kind.MAIN)
        self.assertIn(new, authorizable_services())
        page = self.client.get(reverse("service", args=[new.pk]))
        self.assertContains(page, f'id="auth-{self.owner.pk}-{new.pk}" name="authorized" checked disabled')
        self.assertContains(page, f'id="auth-{self.helper.pk}-{new.pk}" name="authorized"\n')
        self.assertContains(self.toggle(self.owner, new, False), "authorized for every service")

    def test_history_only_services_are_left_out(self):
        self.assertFalse(authorizable_services().filter(on_price_list=False).exists())
        self.assertFalse(authorizable_services().filter(kind=Service.Kind.CUSTOM).exists())

    def test_only_a_manager_changes_authorizations(self):
        self.client.force_login(self.helper_user)
        self.assertEqual(self.toggle(self.helper, self.full_detail, True).status_code, 403)
        self.assertFalse(ServiceAuthorization.objects.exists())
        self.assertContains(self.client.get(reverse("staff-member", args=[self.helper.pk])), "Only a manager can change these.")


class AssignStaffTests(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + datetime.timedelta(days=21)
        inputs = booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1, add_ons=[self.carpet])
        self.job = booking.book(self.customer, self.vehicle, local(self.day), inputs)
        self.url = reverse("appointment-staff", args=[self.job.pk])

    def test_qualified_staff_are_listed_first_and_the_rest_show_what_they_lack(self):
        self.second_helper.authorizations.create(service=self.full_detail)
        self.second_helper.authorizations.create(service=self.carpet)
        choices = staff_choices(self.job)
        self.assertEqual([(c.member, c.qualified) for c in choices], [(self.owner, True), (self.second_helper, True), (self.helper, False)])
        self.assertEqual(choices[2].missing, [self.full_detail, self.carpet])
        page = self.client.get(reverse("appointment", args=[self.job.pk]))
        self.assertContains(page, "Not authorized for: Full Detail, Carpet Extraction")

    def test_a_two_person_crew_covers_the_services_together(self):
        self.helper.authorizations.create(service=self.full_detail)
        self.second_helper.authorizations.create(service=self.carpet)
        self.client.post(self.url, {"staff": [self.helper.pk, self.second_helper.pk]})
        self.assertEqual(set(self.job.assignments.values_list("staff_member", "training_reason")),
                         {(self.helper.pk, ""), (self.second_helper.pk, "")})

    def test_someone_not_yet_authorized_needs_a_warning_and_a_reason(self):
        self.helper.authorizations.create(service=self.full_detail)
        warning = self.client.post(self.url, {"staff": [self.helper.pk]})
        self.assertContains(warning, "no one on this crew is authorized for Carpet Extraction", status_code=400)
        self.assertContains(warning, "Assign anyway", status_code=400)
        self.assertFalse(Assignment.objects.exists())
        no_reason = self.client.post(self.url, {"staff": [self.helper.pk], "confirm": "yes", "training_reason": ""})
        self.assertContains(no_reason, "Give the reason.", status_code=400)
        self.client.post(self.url, {"staff": [self.helper.pk], "confirm": "yes", "training_reason": "Training on carpets"})
        self.assertEqual(self.job.assignments.get().training_reason, "Training on carpets")

    def test_only_a_manager_can_assign_someone_not_yet_authorized(self):
        self.client.force_login(self.helper_user)
        page = self.client.post(self.url, {"staff": [self.helper.pk]})
        self.assertContains(page, "Only a manager can assign someone not yet authorized.", status_code=400)
        self.client.post(self.url, {"staff": [self.helper.pk], "confirm": "yes", "training_reason": "Training"})
        self.assertFalse(Assignment.objects.exists())
        with self.assertRaises(CrewError):
            assign_crew(self.job, [self.helper], training_reason="Training", by_manager=False)

    def test_a_crew_is_one_or_two(self):
        for member in (self.helper, self.second_helper):
            member.authorizations.create(service=self.full_detail)
            member.authorizations.create(service=self.carpet)
        self.client.post(self.url, {"staff": [self.owner.pk, self.helper.pk, self.second_helper.pk]})
        self.assertFalse(Assignment.objects.exists())

    def test_a_different_crew_size_recalculates_the_time_on_site(self):
        self.helper.authorizations.create(service=self.full_detail)
        self.helper.authorizations.create(service=self.carpet)
        self.assertEqual(self.job.crew_size, 1)
        self.client.post(self.url, {"staff": [self.owner.pk, self.helper.pk]})
        self.job.refresh_from_db()
        two = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=1, add_ons=[self.carpet], crew_size=2)
        self.assertEqual((self.job.crew_size, self.job.service_minutes, self.job.setup_minutes, self.job.breakdown_minutes),
                         (2, two.service_minutes, 15, 15))
        self.assertEqual(self.job.time_on_site_minutes, two.time_on_site.total_minutes)
        self.assertEqual(self.job.total_before_tax, two.total_before_tax)  # the price does not change

    def test_a_longer_job_warns_when_it_overlaps_another_that_day(self):
        booking.change_crew_size(self.job, 2)
        later = booking.book(self.customer, self.vehicle, local(self.day, 14, 0), booking.JobInputs(self.monthly, self.crossover, self.two_rows))
        self.assertEqual(booking.overlapping(self.job), [])
        response = self.client.post(self.url, {"staff": [self.owner.pk]}, follow=True)
        self.assertContains(response, "This job overlaps Pat Example")
        self.job.refresh_from_db()
        self.assertEqual(self.job.crew_size, 1)
        self.assertEqual(booking.overlapping(self.job), [later])
