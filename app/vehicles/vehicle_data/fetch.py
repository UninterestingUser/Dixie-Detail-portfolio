"""Downloads, cached in the folder named by the setting
VEHICLE_DATA_CACHE_DIR, so a rerun does not fetch again.

A polite client: it pauses between calls to the same service and retries a
429 or 5xx answer with a growing wait, as ops/lib/bws.sh does for Bitwarden.
A download is cached only once it has been checked, so an error page is
never mistaken for data on the next run.
"""

import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "DixieDetail-vehicle-import/1 (+https://dixiedetail.com)"
TIMEOUT_SECONDS = 120
# The longest wait a Retry-After header may ask for.
MOST_RETRY_AFTER_SECONDS = 300


class FetchError(Exception):
    """A download failed for good."""


def slug(text):
    """A make or vehicle type as part of a cache file name: "Moto Guzzi" ->
    "moto-guzzi"."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def retryable(status):
    return status == 429 or status >= 500


def retry_after(error):
    try:
        return min(float(error.headers.get("Retry-After", 0)), MOST_RETRY_AFTER_SECONDS)
    except (TypeError, ValueError):
        return 0


class Fetcher:
    def __init__(
        self, cache_dir, *, pause_seconds=0, retries=0, backoff_seconds=0, refresh=False,
        opener=None, sleep=time.sleep, log=None,
    ):
        self.cache_dir = Path(cache_dir)
        self.pause_seconds = pause_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        # With refresh, each file is downloaded again once per run.
        self.refresh = refresh
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self.log = log or (lambda text: None)
        self.downloaded = 0
        self.from_cache = 0
        self._fetched = set()
        self._called = set()

    def get(self, url, cache_name, check=None, pace=None):
        """The body at url, from the cache when it is there. check(body)
        raises ValueError if the body is not what was asked for. pace names
        the service to pause between calls to."""
        path = self.cache_dir / cache_name
        if path.exists() and not (self.refresh and path not in self._fetched):
            self.from_cache += 1
            return path.read_bytes()
        if pace is not None:
            if pace in self._called:
                self.sleep(self.pause_seconds)
            self._called.add(pace)
        body = self._download(url)
        if check is not None:
            try:
                check(body)
            except ValueError as error:
                raise FetchError(f"{url}: not the data expected ({error})") from error
        self._store(path, body)
        self._fetched.add(path)
        self.downloaded += 1
        return body

    def _download(self, url):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        attempt = 0
        while True:
            try:
                with self.opener(request, timeout=TIMEOUT_SECONDS) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if not retryable(error.code) or attempt >= self.retries:
                    raise FetchError(f"{url}: HTTP {error.code} {error.reason}") from error
                wait = max(self.backoff_seconds * 2**attempt, retry_after(error))
                attempt += 1
                self.log(f"{url} answered {error.code}; retry {attempt} of {self.retries} in {wait:g} seconds")
                self.sleep(wait)
            except (urllib.error.URLError, TimeoutError) as error:
                raise FetchError(f"{url}: {error}") from error

    def _store(self, path, body):
        """Write the whole file or nothing, so a stopped run never leaves half a
        file in the cache."""
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".part-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(body)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
