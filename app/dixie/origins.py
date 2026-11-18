"""PUBLIC_API_CORS_ORIGINS, read forgivingly (docs/reference/configuration.md).

A browser sends its Origin as a bare scheme and host, such as
https://dixiedetail.com, and the public API compares it exactly. An entry
copied from the address bar, such as "https://dixie-detail.pages.dev/", would
never match, and every call from that site would be refused. So each entry
has spaces and trailing slashes trimmed, and its scheme and host lowercased.
One that still isn't a bare https origin stops the app from starting, with a
message naming it, rather than being refused quietly at every request.
"""

import re

from django.core.exceptions import ImproperlyConfigured

# https, a host name, and an optional port; no path, query or user.
BARE_HTTPS_ORIGIN = re.compile(r"https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?")


def parse_cors_origins(raw, name="PUBLIC_API_CORS_ORIGINS"):
    """The comma-separated origins in raw, normalized, blanks dropped and
    duplicates removed; ImproperlyConfigured for an entry that isn't a bare
    https origin."""
    origins = []
    for entry in (raw or "").split(","):
        origin = entry.strip().rstrip("/").strip()
        if not origin:
            continue
        origin = origin.lower()
        if not BARE_HTTPS_ORIGIN.fullmatch(origin):
            raise ImproperlyConfigured(
                f"{name} has an entry that isn't a bare https origin: {entry.strip()!r}. "
                "Each entry is https:// and a host name only, such as https://dixiedetail.com, "
                "with no path, and the entries are separated by commas."
            )
        if origin not in origins:
            origins.append(origin)
    return origins
