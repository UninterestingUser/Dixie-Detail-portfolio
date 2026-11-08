"""Development and test settings. Every value here is made up.

Never put a real secret here (decision 0045). app/.dockerignore leaves this
file out of the production image, and tools/run-tests.sh checks that the
production image cannot import it.
"""

from pathlib import Path

from dixie.settings_base import *  # noqa: F403

SECRET_KEY = "dev-only-made-up-key-never-used-in-production"
DEBUG = True
# No Google key: development and tests never call Google. Tests replace the
# HTTP call with recorded answers (geo/test_files).
GOOGLE_MAPS_SERVER_KEY = ""
# No calendar key or calendars either: the tests use a fake Google Calendar
# (calendars.testing).
GOOGLE_SERVICE_ACCOUNT_JSON = ""
# Made-up public API values. Tests replace the Turnstile call, so this key
# is never sent anywhere. The website's development server is the only
# browser origin.
TURNSTILE_SECRET_KEY = "made-up-turnstile-secret-for-tests"
OFFLINE_REQUESTS_SIGNING_KEY = "made-up-offline-signing-key-for-tests"
PUBLIC_API_CORS_ORIGINS = ["http://localhost:4321"]
TEST_PHONE_NUMBERS = ["4235550199"]
QUOTE_PHOTO_DIR = Path("/tmp/dixie-quote-photos")
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# The throwaway database that tools/run-tests.sh starts, which shares its
# network with the test container. The script sets the same made-up password.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "127.0.0.1",
        "PORT": 5432,
        "NAME": "dixie",
        "USER": "dixie",
        "PASSWORD": "dixie-dev-password",
    }
}
