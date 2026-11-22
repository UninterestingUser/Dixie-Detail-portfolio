"""The requests-only switch (decision 0128), set with ops/site-mode.sh.

In requests mode every public API path answers 503 except the two the
offline "request a time" form and quote request reach: the website treats a
5xx as "server unavailable" (site/src/scripts/booking/api.js) and offers the
request form, and Cloudflare's held requests still reach the server. The
health page is not under /api/public/, so the public health check stays
green. Used for maintenance, the move to a new host, and outages of a part
of the system the booking flow needs.
"""

import logging
import re

from django.db import DatabaseError
from django.http import JsonResponse

from .http import CALL_US, with_cors

log = logging.getLogger("publicapi")

PREFIX = "/api/public/"
# Still answered in requests mode: the endpoints Cloudflare's offline
# piece replays, in any version of the API.
STILL_OPEN = re.compile(r"^/api/public/v\d+/(time-requests|quote-requests/offline)/?$")


def refused(path):
    return path.startswith(PREFIX) and not STILL_OPEN.match(path)


def requests_only():
    """True in requests mode. A database that can't be asked counts as
    normal: the views then answer for themselves, as they always have."""
    from .models import SiteMode

    try:
        return SiteMode.current() == SiteMode.REQUESTS
    except DatabaseError:
        log.exception("Site mode couldn't be read; treating it as normal")
        return False


class RequestsOnlyMiddleware:
    """Answers 503 on the booking and quote endpoints in requests mode."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if refused(request.path_info) and requests_only():
            response = JsonResponse(
                {"error": "requests_only", "message": f"Online booking is paused just now. You can still send a request. {CALL_US}"},
                status=503,
            )
            response["Retry-After"] = "600"
            response["Cache-Control"] = "no-store"
            return with_cors(request, response, ["GET", "POST", "DELETE"])
        return self.get_response(request)
