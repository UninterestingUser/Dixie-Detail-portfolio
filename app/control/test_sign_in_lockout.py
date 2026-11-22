"""Sign-in lockout (decision 0124): five failed sign-ins for one username or
from one address within 15 minutes refuse sign-ins for 15 minutes, with a
plain message; each lockout is logged; a manager can clear one; a proxy's
own address never locks everyone out."""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from staff.models import StaffMember

from . import lockout
from .models import SignInFailure, SignInLockout

PASSWORD = "an-invented-password-1"
TAILNET = {"X-Dixie-Entrance": "tailnet"}


def tailnet(address):
    return {**TAILNET, "X-Dixie-Client": address}


class LockoutTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.pat = User.objects.create_user("pat", password=PASSWORD)
        cls.sam = User.objects.create_user("sam", password=PASSWORD)
        cls.manager = User.objects.create_user("owner", password=PASSWORD)
        StaffMember.objects.create(name="Owner Person", role=StaffMember.Role.OWNER, user=cls.manager)

    def sign_in(self, username, password, address="100.101.102.103", client=None):
        return (client or Client()).post(reverse("sign-in"), {"username": username, "password": password}, headers=tailnet(address))

    def fail(self, times, username="pat", address="100.101.102.103"):
        return [self.sign_in(username, "wrong-password", address) for _ in range(times)]


class LockoutTests(LockoutTestCase):
    def test_five_failures_for_a_username_lock_it_with_a_plain_message(self):
        answers = self.fail(4)
        self.assertTrue(all(a.status_code == 200 for a in answers))
        self.assertContains(answers[-1], "Your username or password is not right.")
        with self.assertLogs("control.signin", "WARNING") as logged:
            fifth = self.fail(1)[0]
        self.assertEqual(fifth.status_code, 429)
        self.assertNotContains(fifth, "Your username or password is not right.", status_code=429)
        self.assertContains(fifth, "Too many failed sign-ins. Signing in is paused for 15 minutes.", status_code=429)
        self.assertIn("Sign-in lockout: username pat after 5 failed sign-ins", logged.output[0])
        # The right password is refused too, from another address, without being checked.
        with mock.patch("django.contrib.auth.forms.authenticate") as checked:
            refused = self.sign_in("pat", PASSWORD, "100.64.9.9")
        self.assertEqual(refused.status_code, 429)
        checked.assert_not_called()
        # Another username is unaffected.
        self.assertEqual(self.sign_in("sam", PASSWORD, "100.64.9.9").status_code, 302)

    def test_five_failures_from_one_address_lock_that_address(self):
        for name in ("pat", "sam", "nobody", "admin", "root"):
            self.fail(1, username=name, address="100.70.0.1")
        lock = SignInLockout.objects.get(kind="address")
        self.assertEqual(lock.value, "100.70.0.1")
        self.assertEqual(self.sign_in("sam", PASSWORD, "100.70.0.1").status_code, 429)
        self.assertEqual(self.sign_in("sam", PASSWORD, "100.70.0.2").status_code, 302)

    def test_the_lockout_ends_after_its_minutes(self):
        self.fail(5)
        later = timezone.now() + datetime.timedelta(minutes=16)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertEqual(self.sign_in("pat", PASSWORD).status_code, 302)

    def test_failures_outside_the_window_dont_count(self):
        earlier = timezone.now() - datetime.timedelta(minutes=20)
        for _ in range(4):
            SignInFailure.objects.create(username="pat", address="100.101.102.103", at=earlier)
        self.fail(4)
        self.assertFalse(SignInLockout.objects.exists())

    def test_a_good_sign_in_clears_the_count(self):
        self.fail(4)
        self.assertEqual(self.sign_in("pat", PASSWORD).status_code, 302)
        self.fail(4)
        self.assertFalse(SignInLockout.objects.exists())

    def test_the_username_is_matched_whatever_its_case_or_spaces(self):
        self.fail(5, username=" PAT ")
        self.assertEqual(self.sign_in("pat", PASSWORD, "100.64.9.9").status_code, 429)

    @override_settings(SIGN_IN_LOCKOUT_FAILURES=3, SIGN_IN_LOCKOUT_MINUTES=60)
    def test_the_numbers_are_settings(self):
        third = self.fail(3)[-1]
        self.assertContains(third, "paused for 60 minutes", status_code=429)
        lock = SignInLockout.objects.get(kind="username")
        self.assertEqual(lock.until - lock.started_at, datetime.timedelta(minutes=60))


class ProxyAddressTests(LockoutTestCase):
    def test_a_proxy_address_never_locks_everyone_out(self):
        # tailscale serve passing no client address: every sign-in seems to
        # come from Docker's gateway. Only the username limit applies.
        for name in ("pat", "sam", "nobody", "admin", "root", "guest"):
            self.fail(1, username=name, address="172.18.0.1")
        self.assertFalse(SignInLockout.objects.filter(kind="address").exists())
        self.assertEqual(self.sign_in("sam", PASSWORD, "172.18.0.1").status_code, 302)
        self.assertEqual(SignInFailure.objects.exclude(address="").count(), 0)

    def test_the_address_comes_from_caddy_on_the_tailnet_door_only(self):
        request = mock.Mock(headers={"X-Dixie-Entrance": "public", "X-Dixie-Client": "100.1.1.1"}, META={"REMOTE_ADDR": "172.18.0.5"})
        self.assertEqual(lockout.client_address(request), "172.18.0.5")
        request.headers = {"X-Dixie-Entrance": "tailnet", "X-Dixie-Client": "100.1.1.1"}
        self.assertEqual(lockout.client_address(request), "100.1.1.1")
        request.headers = {"X-Dixie-Entrance": "tailnet", "X-Dixie-Client": "not an address"}
        self.assertEqual(lockout.client_address(request), "")
        self.assertTrue(lockout.personal("100.101.102.103"))
        for address in ("", "127.0.0.1", "172.18.0.1", "192.0.2.10", "10.0.0.2", "::1"):
            self.assertFalse(lockout.personal(address), address)


class ClearTests(LockoutTestCase):
    def test_a_manager_sees_and_clears_a_lockout(self):
        self.fail(5)
        client = Client()
        client.force_login(self.manager)
        page = client.get(reverse("sign-in-lockouts"), headers=TAILNET)
        self.assertContains(page, "Username: pat")
        self.assertContains(page, "Address: 100.101.102.103")
        lock = SignInLockout.objects.get(kind="username")
        with self.assertLogs("control.signin", "WARNING") as logged:
            client.post(reverse("sign-in-lockout-clear", args=[lock.pk]), headers=TAILNET)
        self.assertIn("Sign-in lockout cleared: username pat, by owner", logged.output[0])
        lock.refresh_from_db()
        self.assertEqual(lock.cleared_by, self.manager)
        # The address is still locked, so sign in from another one.
        self.assertEqual(self.sign_in("pat", PASSWORD, "100.64.9.9").status_code, 302)
        # The failures behind it went too: one more mistake doesn't lock again.
        self.fail(1, address="100.64.9.9")
        self.assertFalse(SignInLockout.objects.filter(kind="username", cleared_at=None).exists())

    def test_only_a_manager_can(self):
        self.fail(5)
        client = Client()
        client.force_login(self.sam)
        self.assertEqual(client.get(reverse("sign-in-lockouts"), headers=TAILNET).status_code, 403)
        lock = SignInLockout.objects.get(kind="username")
        self.assertEqual(client.post(reverse("sign-in-lockout-clear", args=[lock.pk]), headers=TAILNET).status_code, 403)
        lock.refresh_from_db()
        self.assertIsNone(lock.cleared_at)

    def test_the_account_page_links_it_for_managers(self):
        client = Client()
        client.force_login(self.manager)
        self.assertContains(client.get(reverse("account"), headers=TAILNET), "Sign-in lockouts")
