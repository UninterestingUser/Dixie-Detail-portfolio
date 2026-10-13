"""Settings for the Dixie Detail core app.

Non-secret settings come from environment variables (set from .env by
compose.yaml). Secrets are read from files whose paths are given by *_FILE
variables; the files are mounted from memory by dixie-stack.service.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def read_secret(env_name):
    path = os.environ.get(env_name)
    if not path:
        raise ImproperlyConfigured(f"{env_name} is not set")
    return Path(path).read_text().strip()


SECRET_KEY = read_secret("DJANGO_SECRET_KEY_FILE")
DEBUG = False
# "localhost" is for the container's own health check.
ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()
] + ["localhost"]

INSTALLED_APPS = [
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.PublicEntranceMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "dixie.urls"
WSGI_APPLICATION = "dixie.wsgi.application"

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
