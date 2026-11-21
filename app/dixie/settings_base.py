"""Settings shared by production (dixie.settings) and development and tests
(dixie.settings_dev). Nothing here is secret or differs between the two.
"""

import os
from pathlib import Path

from dixie.origins import parse_cors_origins

# The repository's data/ folder: the price matrix and the launch values the
# pricebook and scheduling read. It sits beside app/ in the repository, and
# compose.yaml and tools/run-tests.sh mount it read-only at /srv/data, beside
# the app at /srv/app.
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Where import_vehicle_data caches what it downloads, so a rerun does not fetch
# again. Outside the repository: on the server, a host folder mounted here
# into the one-off container (docs/operations/importing-vehicle-data.md).
VEHICLE_DATA_CACHE_DIR = Path(os.environ.get("VEHICLE_DATA_CACHE_DIR", "/srv/vehicle-data"))

# The two Google calendars (decisions 0006 and 0098), by calendar ID, from
# .env. Not secret. Empty in development and tests, which never call Google.
GOOGLE_CALENDAR_JOBS_ID = os.environ.get("GOOGLE_CALENDAR_JOBS_ID", "")
GOOGLE_CALENDAR_TIME_OFF_ID = os.environ.get("GOOGLE_CALENDAR_TIME_OFF_ID", "")
# The service account's JSON key, a secret: dixie.settings reads it from its
# file; empty means the calendar sync is not connected.
GOOGLE_SERVICE_ACCOUNT_JSON = ""


def env_list(name):
    """A comma-separated setting from .env as a list, blanks dropped."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def env_int(name, default):
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


# The public API (docs/reference/public-api.md), settings from .env.
# The website's addresses, such as https://dixiedetail.com: the only origins
# a browser may call the public API from (CORS). Spaces and a trailing slash
# are trimmed; an entry that still isn't a bare https origin stops the app
# from starting (dixie/origins.py). dixie.wsgi logs the list at startup.
PUBLIC_API_CORS_ORIGINS = parse_cors_origins(os.environ.get("PUBLIC_API_CORS_ORIGINS", ""))
# How long a website quote can be booked, in minutes.
QUOTE_LIFETIME_MINUTES = env_int("QUOTE_LIFETIME_MINUTES", 120)
# Quote request photos (decision 0099): how many per request, how large each
# may be as sent, and how many days after the request is closed they are kept.
QUOTE_REQUEST_MAX_PHOTOS = env_int("QUOTE_REQUEST_MAX_PHOTOS", 6)
QUOTE_REQUEST_PHOTO_MAX_MB = env_int("QUOTE_REQUEST_PHOTO_MAX_MB", 15)
QUOTE_REQUEST_PHOTO_DAYS = env_int("QUOTE_REQUEST_PHOTO_DAYS", 90)
# Address lookup sessions (decision 0115): how many address lookups one
# session allows, and for how many minutes after it opens.
ADDRESS_LOOKUP_SESSION_LOOKUPS = env_int("ADDRESS_LOOKUP_SESSION_LOOKUPS", 10)
ADDRESS_LOOKUP_SESSION_MINUTES = env_int("ADDRESS_LOOKUP_SESSION_MINUTES", 30)
# Where the photos are kept in the app container: the host folder
# /srv/dixie-quote-photos is mounted here (compose.yaml).
QUOTE_PHOTO_DIR = Path(os.environ.get("QUOTE_PHOTO_DIR", "/srv/quote-photos"))
# Mobile numbers whose website bookings and requests are marked test
# records, 10 digits each.
TEST_PHONE_NUMBERS = env_list("TEST_PHONE_NUMBERS")
# The public address api_smoke_test books through, and the Google place ID of
# a public place in the service area that it books at.
API_SMOKE_TEST_URL = os.environ.get("API_SMOKE_TEST_URL", "https://api.dixiedetail.com")
API_SMOKE_TEST_PLACE_ID = os.environ.get("API_SMOKE_TEST_PLACE_ID", "")
# Requests a visitor address may make per window, by kind (public-api.md).
# Fixed here rather than in .env: changing them is a code review.
PUBLIC_API_RATE_LIMITS = {
    # kind: (requests, window in minutes)
    "read": (600, 10),
    "quote": (120, 10),
    "address": (30, 10),
    "lookup_session": (10, 60),
    "booking": (10, 60),
    "quote_request": (6, 60),
    "upload_session": (10, 60),
    "photo": (60, 60),
    # Replayed offline requests all come from Cloudflare, and are signed.
    "offline": (600, 10),
}
# Secrets: dixie.settings reads them from their files. Empty means the
# Turnstile check fails, so nothing is booked, and offline requests are
# refused.
TURNSTILE_SECRET_KEY = ""
OFFLINE_REQUESTS_SIGNING_KEY = ""
CLOUDFLARE_PAGES_DEPLOY_HOOK = ""

INSTALLED_APPS = [
    # The Django admin, for superusers only (decision 0046).
    "dixie.apps.SuperuserAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    "core",
    "control",
    "customers",
    "vehicles",
    "pricebook",
    "promotions",
    "appointments",
    "billing",
    "staff",
    "bookkeeping",
    "marketing",
    "messaging",
    "importer",
    "geo",
    "scheduling",
    "calendars.apps.CalendarsConfig",
    "publicapi",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.PublicEntranceMiddleware",
    # After the entrance check, so the public door never serves static files.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page needs a signed-in user unless its view says otherwise
    # (decision 0052).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Records the signed-in user on change history (decision 0050).
    "simple_history.middleware.HistoryRequestMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "control.context_processors.brand",
            ],
        },
    }
]

# Static files are served by the app itself through WhiteNoise, straight from
# each app's static/ folder, so the read-only container needs no collect step
# (decision 0068).
STATIC_URL = "/static/"
WHITENOISE_USE_FINDERS = True

# Sign-in (decision 0052).
LOGIN_URL = "sign-in"
LOGIN_REDIRECT_URL = "schedule"
LOGOUT_REDIRECT_URL = "sign-in"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Uploads larger than this go to a temporary file in /tmp (memory in the
# container) instead of process memory. Photos are capped by
# QUOTE_REQUEST_PHOTO_MAX_MB before Django reads them (publicapi.photos).
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440

# HTTPS behind tailscale serve and Caddy (decision 0068). tailscale serve ends
# HTTPS and hands the request to Caddy's control-app port, which sets
# X-Forwarded-Proto to https; Caddy's public port sets it from its own plain
# HTTP connection. Only Caddy can reach the app, so the header can be trusted.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True


def trusted_origins(hosts):
    """The HTTPS origins forms may be posted from: each allowed host name
    except the server's own local names, which are only used for checks."""
    return [f"https://{host}" for host in hosts if host not in ("localhost", "127.0.0.1")]

ROOT_URLCONF = "dixie.urls"
WSGI_APPLICATION = "dixie.wsgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
