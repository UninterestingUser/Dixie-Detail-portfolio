"""The one place the app calls an outside JSON service. Tests replace
request_json, so no test touches the network."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "dixie-detail/1.0"


class FetchError(Exception):
    """The service could not be reached or did not answer with JSON."""


def request_json(url, *, method="GET", params=None, headers=None, body=None, timeout=10):
    """Call url and return its JSON answer. Keys go in headers, never in the
    URL, so they never appear in a log."""
    if params:
        url = f"{url}?{urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else None
    all_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    if data is not None:
        all_headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=data, method=method, headers=all_headers), timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        raise FetchError(f"{url.split('?')[0]} answered {error.code}") from error
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise FetchError(f"{url.split('?')[0]} could not be reached: {error}") from error
