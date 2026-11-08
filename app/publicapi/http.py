"""What every public API view shares (docs/reference/public-api.md):

- CORS: a browser may call the API only from an origin in
  PUBLIC_API_CORS_ORIGINS. A request from any other origin is refused; a
  request with no Origin header, such as the smoke test, is allowed.
- Rate limits per visitor address, counted in PostgreSQL so every gunicorn
  worker sees the same count. The address is kept only as a keyed hash.
- Size limits and strict JSON: an object of known fields only.
- Generic errors: a code and a plain sentence, never a traceback, a rule
  or anything from a customer's record.
"""

import datetime
import functools
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import SuspiciousOperation
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.csrf import csrf_exempt

from .models import RateCount

log = logging.getLogger("publicapi")

# Bodies larger than this are refused before they are read. Photos have
# their own limit (QUOTE_REQUEST_PHOTO_MAX_MB).
MAX_JSON_BYTES = 16_384
CALL_US = "Please try again, or call or text (423) 380-9120."


class ApiError(Exception):
    """An answer other than success: status, code, message and any extra
    fields, such as a fresh quote."""

    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def response(self):
        return JsonResponse({"error": self.code, "message": self.message, **self.extra}, status=self.status)


def bad_request(field, message="Something in the form isn't right. Please check it and try again."):
    return ApiError(400, "bad_request", message, field=field)


def not_found(message="That wasn't found. Please start again."):
    return ApiError(404, "not_found", message)


def visitor_address(request):
    """The visitor's address: Cloudflare's CF-Connecting-IP on the public
    door, which only Cloudflare reaches; the connection's own address
    otherwise."""
    if request.headers.get("X-Dixie-Entrance", "public") != "tailnet":
        forwarded = request.headers.get("CF-Connecting-IP", "").strip()
        if forwarded:
            return forwarded[:64]
    return request.META.get("REMOTE_ADDR", "")


def visitor_key(request):
    """A keyed hash of the visitor's address, so no address is stored."""
    return hmac.new(settings.SECRET_KEY.encode(), visitor_address(request).encode(), hashlib.sha256).hexdigest()[:32]


def check_rate(request, kind):
    """Count one request of kind from this visitor, or refuse it once the
    window's limit is reached."""
    limit, minutes = settings.PUBLIC_API_RATE_LIMITS[kind]
    now = timezone.now()
    window = datetime.timedelta(minutes=minutes)
    start = datetime.datetime.fromtimestamp((now.timestamp() // window.total_seconds()) * window.total_seconds(), datetime.UTC)
    key = visitor_key(request)
    with transaction.atomic():
        try:
            with transaction.atomic():
                RateCount.objects.create(kind=kind, visitor=key, window_start=start, count=1)
                return
        except IntegrityError:
            pass
        updated = RateCount.objects.filter(kind=kind, visitor=key, window_start=start, count__lt=limit).update(count=F("count") + 1)
    if not updated:
        raise ApiError(429, "rate_limited", "That's a lot of requests in a short time. Please wait a few minutes and try again.")


def origin_allowed(origin):
    return origin in settings.PUBLIC_API_CORS_ORIGINS


def with_cors(request, response, methods):
    origin = request.headers.get("Origin")
    if origin and origin_allowed(origin):
        response["Access-Control-Allow-Origin"] = origin
        response["Access-Control-Allow-Methods"] = ", ".join(sorted({*methods, "OPTIONS"}))
        response["Access-Control-Allow-Headers"] = "Content-Type"
        response["Access-Control-Max-Age"] = "600"
    patch_vary_headers(response, ["Origin"])
    response["X-Content-Type-Options"] = "nosniff"
    return response


def read_json(request):
    """The request's JSON object. Refuses a body too large, not JSON, or
    not an object."""
    if not request.content_type == "application/json":
        raise ApiError(415, "bad_request", "Send the form as JSON.")
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = MAX_JSON_BYTES + 1
    if length > MAX_JSON_BYTES:
        raise ApiError(413, "too_large", "That form is too large.")
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ApiError(400, "bad_request", "Something in the form isn't right. Please check it and try again.") from error
    if not isinstance(data, dict):
        raise bad_request("body")
    return data


def api_view(methods, limit, cache_seconds=None):
    """A public API view: no sign-in, no CSRF cookie (no cookies at all),
    CORS for the site's origins, a rate limit of the given kind, and JSON
    errors. The view returns a dict (200), a (status, dict) pair or a
    response."""
    methods = tuple(methods)

    def decorate(view):
        @login_not_required
        @csrf_exempt
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            origin = request.headers.get("Origin")
            if request.method == "OPTIONS":
                if not origin or not origin_allowed(origin):
                    return with_cors(request, HttpResponse(status=403), methods)
                return with_cors(request, HttpResponse(status=204), methods)
            try:
                if origin and not origin_allowed(origin):
                    raise ApiError(403, "forbidden", "This address can't be used from that website.")
                if request.method not in methods:
                    raise ApiError(405, "method_not_allowed", "That isn't allowed here.")
                check_rate(request, limit)
                answer = view(request, *args, **kwargs)
            except ApiError as error:
                response = error.response()
            except SuspiciousOperation:
                # Django's own limits on a request, such as too many fields.
                response = ApiError(400, "bad_request", "Something in the form isn't right. Please check it and try again.").response()
            except Exception:
                log.exception("public API error on %s", request.path)
                response = ApiError(500, "server_error", f"Something went wrong on our side. {CALL_US}").response()
            else:
                if isinstance(answer, HttpResponse):
                    response = answer
                elif isinstance(answer, tuple):
                    response = JsonResponse(answer[1], status=answer[0])
                else:
                    response = JsonResponse(answer)
            if cache_seconds and response.status_code == 200:
                response["Cache-Control"] = f"public, max-age={cache_seconds}"
            elif not response.has_header("Cache-Control"):
                response["Cache-Control"] = "no-store"
            return with_cors(request, response, methods)

        return wrapped

    return decorate
