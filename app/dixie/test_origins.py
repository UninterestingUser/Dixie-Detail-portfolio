"""PUBLIC_API_CORS_ORIGINS is read forgivingly (dixie/origins.py)."""

import importlib
import logging

import pytest
from django.core.exceptions import ImproperlyConfigured

from dixie.origins import parse_cors_origins


def test_bare_origins_are_kept_as_they_are():
    assert parse_cors_origins("https://dixiedetail.com,https://www.dixiedetail.com") == [
        "https://dixiedetail.com",
        "https://www.dixiedetail.com",
    ]


def test_a_trailing_slash_is_trimmed():
    # The setting that refused every call from staging with a 403.
    assert parse_cors_origins("https://dixie-detail.pages.dev/") == ["https://dixie-detail.pages.dev"]
    assert parse_cors_origins("https://example.com//") == ["https://example.com"]


def test_spaces_blanks_case_and_repeats_are_tidied():
    raw = "  https://dixiedetail.com , , HTTPS://Dixie-Detail.pages.dev/ ,https://dixiedetail.com/,"
    assert parse_cors_origins(raw) == ["https://dixiedetail.com", "https://dixie-detail.pages.dev"]


def test_a_port_is_allowed():
    assert parse_cors_origins("https://example.com:8443/") == ["https://example.com:8443"]


def test_empty_means_no_origins():
    assert parse_cors_origins("") == []
    assert parse_cors_origins(None) == []
    assert parse_cors_origins(" , ") == []


@pytest.mark.parametrize(
    "entry",
    [
        "http://dixiedetail.com",
        "dixiedetail.com",
        "https://dixiedetail.com/book/",
        "https://dixiedetail.com?x=1",
        "https://user@dixiedetail.com",
        "https://",
        "https://dixie detail.com",
        "https://dixiedetail.com https://www.dixiedetail.com",
    ],
)
def test_an_entry_that_isnt_a_bare_https_origin_stops_startup_naming_it(entry):
    with pytest.raises(ImproperlyConfigured) as raised:
        parse_cors_origins(f"https://dixiedetail.com, {entry}")
    message = str(raised.value)
    assert "PUBLIC_API_CORS_ORIGINS" in message
    assert repr(entry.strip()) in message


def test_settings_read_the_setting_through_the_parser(monkeypatch):
    import dixie.settings_base as base

    monkeypatch.setenv("PUBLIC_API_CORS_ORIGINS", " https://dixiedetail.com/ ,https://dixie-detail.pages.dev/")
    try:
        assert importlib.reload(base).PUBLIC_API_CORS_ORIGINS == ["https://dixiedetail.com", "https://dixie-detail.pages.dev"]
        monkeypatch.setenv("PUBLIC_API_CORS_ORIGINS", "https://dixiedetail.com/book/")
        with pytest.raises(ImproperlyConfigured, match="https://dixiedetail.com/book/"):
            importlib.reload(base)
    finally:
        monkeypatch.delenv("PUBLIC_API_CORS_ORIGINS")
        importlib.reload(base)


def test_startup_logs_the_origins_in_use(settings, caplog, monkeypatch):
    import sys

    import django.core.wsgi

    # Django is already set up here; setting it up again would reset logging
    # and drop the log capture, so the import below gets a stand-in.
    monkeypatch.setattr(django.core.wsgi, "get_wsgi_application", lambda: None)
    monkeypatch.delitem(sys.modules, "dixie.wsgi", raising=False)
    settings.PUBLIC_API_CORS_ORIGINS = ["https://dixiedetail.com", "https://dixie-detail.pages.dev"]
    with caplog.at_level(logging.INFO, logger="dixie.startup"):
        importlib.import_module("dixie.wsgi")
    assert "Public API CORS origins: https://dixiedetail.com, https://dixie-detail.pages.dev" in caplog.text
