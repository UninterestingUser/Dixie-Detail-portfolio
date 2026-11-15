"""Asking Cloudflare Pages to rebuild the website, so the prices it shows
match the pricebook in effect (docs/reference/website-and-seo.md).

The site reads the published pricebook from the public API when it is
built. A rebuild is asked for:

- when a pricebook version is published (publishing.publish, after the
  transaction commits), so a version effective today shows within minutes;
- every night by `rebuild_website --if-due`, when a version published
  earlier takes effect that day.

The deploy hook is a URL in the Bitwarden secret CLOUDFLARE_PAGES_DEPLOY_HOOK.
Without it nothing is asked for. A failed call is logged and never stops a
publish: the nightly check and the next publish ask again.
"""

import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from .models import PricebookVersion

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15


def request_rebuild(reason):
    """POST to the deploy hook. Returns True when Cloudflare accepted it,
    False when there is no hook or the call failed (logged)."""
    hook = settings.CLOUDFLARE_PAGES_DEPLOY_HOOK
    if not hook:
        logger.info("Website rebuild not asked for (%s): no deploy hook is set.", reason)
        return False
    request = urllib.request.Request(hook, data=b"", method="POST", headers={"User-Agent": "dixie-detail-app"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            ok = 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        # The hook's URL is a secret: log the error's kind, never the URL.
        logger.warning("Website rebuild request failed (%s): %s", reason, type(error).__name__)
        return False
    if ok:
        logger.info("Website rebuild asked for: %s.", reason)
    else:
        logger.warning("Website rebuild request refused (%s): HTTP %s.", reason, response.status)
    return ok


def due_today(today=None):
    """The published version that takes effect today, when it was published
    before today, so the rebuild at publish showed the version before it."""
    today = today or timezone.localdate()
    version = PricebookVersion.current(today)
    if version is None or version.effective_date != today:
        return None
    if timezone.localtime(version.published_at).date() >= today:
        return None
    return version
