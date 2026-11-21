"""Address lookup sessions (decision 0115, public-api.md).

Each public address lookup (POST addresses) asks Google for Place Details,
which the business pays for past the free monthly amount. A lookup needs a
session, opened with a Turnstile token at the booking form's location step:
it allows ADDRESS_LOOKUP_SESSION_LOOKUPS lookups within
ADDRESS_LOOKUP_SESSION_MINUTES, so a script can't run lookups in a loop
without solving Turnstile again and again. The rate limit still applies on
top, and the lookups together stop at the day's public share
(geo.google.PublicShareUsed).
"""

import datetime

from django.conf import settings
from django.db.models import F
from django.utils import timezone

from . import turnstile, validate
from .http import ApiError, visitor_key
from .models import LookupSession

SESSION_ENDED = "Your address search has timed out. Please pick your address again."


def open_session(request, data):
    validate.only(data, ["turnstile"])
    turnstile.check(request, data["turnstile"])
    session = LookupSession.objects.create(
        visitor=visitor_key(request),
        expires_at=timezone.now() + datetime.timedelta(minutes=settings.ADDRESS_LOOKUP_SESSION_MINUTES),
    )
    return 201, {
        "session": session.token,
        "expires_at": session.expires_at.isoformat(),
        "lookups": settings.ADDRESS_LOOKUP_SESSION_LOOKUPS,
    }


def use(token):
    """Count one lookup on the session, or refuse with lookup_session when
    there is none, it has expired or its lookups are used. The site opens a
    new one and tries once more."""
    if not isinstance(token, str) or not token or len(token) > 40:
        raise ApiError(403, "lookup_session", SESSION_ENDED)
    used = LookupSession.objects.filter(
        token=token, expires_at__gt=timezone.now(), lookups__lt=settings.ADDRESS_LOOKUP_SESSION_LOOKUPS,
    ).update(lookups=F("lookups") + 1)
    if not used:
        raise ApiError(403, "lookup_session", SESSION_ENDED)
