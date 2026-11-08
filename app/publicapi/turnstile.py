"""The Cloudflare Turnstile check on bookings, quote requests and upload
sessions. The website's widget gives a token; the server sends it, with the
secret key (Bitwarden secret TURNSTILE_SECRET_KEY) and the visitor's
address, to Cloudflare's siteverify and accepts only a success. A token
works once and expires after 5 minutes, Cloudflare's own rules.

api_smoke_test can't solve a widget, so it makes a one-time pass in the
database (SmokeTestPass) and sends that instead; only something with the
database can make one."""

import logging

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from geo import http as outside

from .http import ApiError, visitor_address
from .models import SmokeTestPass

log = logging.getLogger("publicapi")
SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SMOKE_TEST_PREFIX = "smoke-test:"


def failed():
    return ApiError(403, "turnstile_failed", "We couldn't confirm the form was sent by a person. Please try again.")


def siteverify(token, remote_ip):
    """Cloudflare's answer for token, as a dict. Tests replace this."""
    body = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        body["remoteip"] = remote_ip
    return outside.request_json(SITEVERIFY_URL, method="POST", body=body, timeout=10)


def use_smoke_test_pass(token):
    """True when token is a live smoke test pass with a use left, taking one use."""
    used = SmokeTestPass.objects.filter(token=token, expires_at__gt=timezone.now(), uses_left__gt=0).update(uses_left=F("uses_left") - 1)
    return bool(used)


def check(request, token):
    """Accept the Turnstile token, or raise ApiError. Returns True for a
    smoke test pass, False for a real token."""
    if not isinstance(token, str) or not 1 <= len(token) <= 2048:
        raise failed()
    if token.startswith(SMOKE_TEST_PREFIX):
        if use_smoke_test_pass(token.removeprefix(SMOKE_TEST_PREFIX)):
            return True
        raise failed()
    if not settings.TURNSTILE_SECRET_KEY:
        log.error("Turnstile token refused: no TURNSTILE_SECRET_KEY")
        raise failed()
    try:
        answer = siteverify(token, visitor_address(request))
    except outside.FetchError as error:
        log.warning("Turnstile siteverify failed: %s", error)
        raise ApiError(503, "unavailable", "We couldn't check the form just now. Please try again in a minute.") from error
    if not answer.get("success"):
        log.info("Turnstile token refused: %s", answer.get("error-codes"))
        raise failed()
    return False
