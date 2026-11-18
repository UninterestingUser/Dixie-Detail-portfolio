import logging
import os

from django.conf import settings
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dixie.settings")
application = get_wsgi_application()

# The origins the public API answers browsers from, so a wrong
# PUBLIC_API_CORS_ORIGINS shows in the app's log at startup.
logging.getLogger("dixie.startup").info(
    "Public API CORS origins: %s", ", ".join(settings.PUBLIC_API_CORS_ORIGINS) or "none (no website can call the public API)"
)
