"""Settings shared by production (dixie.settings) and development and tests
(dixie.settings_dev). Nothing here is secret or differs between the two.
"""

from pathlib import Path

# The repository's data/ folder: the price matrix and the launch values the
# pricebook and scheduling read. It sits beside app/ in the repository, and
# compose.yaml and tools/run-tests.sh mount it read-only at /srv/data, beside
# the app at /srv/app.
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "simple_history",
    "core",
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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.PublicEntranceMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Records the signed-in user on change history (decision 0050).
    "simple_history.middleware.HistoryRequestMiddleware",
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
