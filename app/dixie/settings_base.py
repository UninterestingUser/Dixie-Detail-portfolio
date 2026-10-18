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
