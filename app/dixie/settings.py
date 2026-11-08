"""Production settings for the Dixie Detail core app.

Non-secret settings come from environment variables (set from .env by
compose.yaml). Secrets are read from files whose paths are given by *_FILE
variables; the files are mounted from memory by dixie-stack.service.
Development and tests use dixie.settings_dev instead.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from dixie.settings_base import *  # noqa: F403


def read_secret(env_name):
    path = os.environ.get(env_name)
    if not path:
        raise ImproperlyConfigured(f"{env_name} is not set")
    return Path(path).read_text().strip()


def read_optional_secret(env_name):
    """A secret that may not exist yet: empty when its file is empty."""
    path = os.environ.get(env_name)
    return Path(path).read_text().strip() if path and Path(path).exists() else ""


SECRET_KEY = read_secret("DJANGO_SECRET_KEY_FILE")
# The server-side Google Maps Platform key (Place Details and Routes). Until
# the Bitwarden secret exists the file is empty, and the app works without
# Google: place lookups fail and drive times are estimated (geo.google).
GOOGLE_MAPS_SERVER_KEY = read_optional_secret("GOOGLE_MAPS_SERVER_KEY_FILE")
# The Google service account's JSON key for the two calendars (decision
# 0098). Empty until the Bitwarden secret exists: the sync then waits, and
# the control app says the calendars are not connected.
GOOGLE_SERVICE_ACCOUNT_JSON = read_optional_secret("GOOGLE_SERVICE_ACCOUNT_JSON_FILE")
# The Cloudflare Turnstile secret key, which checks the token on every
# booking, quote request and upload session (public-api.md). Empty until the
# Bitwarden secret exists: those requests are then refused.
TURNSTILE_SECRET_KEY = read_optional_secret("TURNSTILE_SECRET_KEY_FILE")
# The key Cloudflare's offline piece signs replayed "request a time" forms
# with (decision 0100). Empty until it exists: offline requests are refused.
OFFLINE_REQUESTS_SIGNING_KEY = read_optional_secret("OFFLINE_REQUESTS_SIGNING_KEY_FILE")
DEBUG = False
# "localhost" is for the container's own health check.
ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()
] + ["localhost"]
# The tailnet address, so signing in over HTTPS passes Django's origin check.
CSRF_TRUSTED_ORIGINS = trusted_origins(ALLOWED_HOSTS)  # noqa: F405

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "NAME": os.environ.get("POSTGRES_DB", "dixie"),
        "USER": os.environ.get("POSTGRES_USER", "dixie"),
        "PASSWORD": read_secret("POSTGRES_PASSWORD_FILE"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
