"""Development and test settings. Every value here is made up.

Never put a real secret here (decision 0045). app/.dockerignore leaves this
file out of the production image, and tools/run-tests.sh checks that the
production image cannot import it.
"""

from dixie.settings_base import *  # noqa: F403

SECRET_KEY = "dev-only-made-up-key-never-used-in-production"
DEBUG = True
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
