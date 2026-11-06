"""Shared set-up for the address, tax and drive-time tests: a fake for the
one HTTP call (geo.http.request_json) that answers from geo/test_files, and
the Tennessee rates and boundaries loaded from those files. No test touches
the network."""

import json
from pathlib import Path
from unittest import mock

from django.test import override_settings

from billing import tax_rates

FILES = Path(__file__).resolve().parent / "test_files"
MADE_UP_KEY = "made-up-google-key-for-tests"


def load(name):
    return json.loads((FILES / name).read_text())


class FakeServices:
    """Answers request_json like the real services, from the test files.

    places: {place_id: file name}; census: {street: file name};
    routes: a file name, or None to fail. Records every call in calls.
    """

    def __init__(self, places=None, census=None, routes="routes_answer.json"):
        self.places = places or {}
        self.census = census or {}
        self.routes = routes
        self.calls = []

    def __call__(self, url, **kwargs):
        from geo import http

        self.calls.append((url, kwargs))
        if url.startswith("https://places.googleapis.com/"):
            name = self.places.get(url.rsplit("/", 1)[1])
            if name is None:
                raise http.FetchError("places answered 404")
            return load(name)
        if url.startswith("https://geocoding.geo.census.gov/"):
            return load(self.census.get(kwargs["params"]["street"], "census_no_match.json"))
        if url.startswith("https://routes.googleapis.com/"):
            if self.routes is None:
                raise http.FetchError("routes could not be reached")
            return load(self.routes)
        if url.startswith("https://tnmap.tn.gov/"):
            where = kwargs["params"]["where"]
            return load("tn_unincorporated.geojson" if "Unincorporated" in where else "tn_five_counties.geojson")
        raise AssertionError(f"unexpected call to {url}")

    def urls(self, prefix):
        return [call for call in self.calls if call[0].startswith(prefix)]

    def patch(self):
        return mock.patch("geo.http.request_json", side_effect=self)


def with_google_key(test):
    return override_settings(GOOGLE_MAPS_SERVER_KEY=MADE_UP_KEY)(test)


def import_fixture_rates(today=None):
    """Load the test files' Tennessee rates and boundaries, and Georgia's 0%."""
    with FakeServices().patch():
        rows = tax_rates.fetch_rows(geometry=True)
    return tax_rates.apply(rows, mode="import", today=today)
