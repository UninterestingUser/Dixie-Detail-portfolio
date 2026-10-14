"""Settings shared by production (dixie.settings) and development and tests
(dixie.settings_dev). Nothing here is secret or differs between the two.
"""

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
