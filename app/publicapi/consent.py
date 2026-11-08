"""The text consent wording, by version, from data/consent-wording.yaml.
The website shows the current version and sends it back with the two
answers; the server records each answer with the words of that version
from the file, never words from the browser (text-messages.md)."""

from functools import cache

import yaml
from django.conf import settings
from django.utils import timezone

from customers.models import Consent

from . import validate
from .http import bad_request

KINDS = {"appointment": Consent.Kind.APPOINTMENT, "follow_up": Consent.Kind.FOLLOW_UP}


@cache
def wording():
    return yaml.safe_load((settings.DATA_DIR / "consent-wording.yaml").read_text())


def current():
    data = wording()
    version = data["current"]
    return {"version": version, **{kind: data["versions"][version][kind] for kind in KINDS}, "links": data["links"]}


def parse(value, field="consents"):
    """{"version": ..., "appointment": bool, "follow_up": bool}, checked."""
    validate.only(value, ["version", *KINDS], field=field)
    version = value["version"]
    if not isinstance(version, str) or version not in wording()["versions"]:
        raise bad_request(f"{field}.version", "The consent wording has changed. Please reload the page.")
    return {"version": version, **{kind: validate.boolean(value[kind], f"{field}.{kind}") for kind in KINDS}}


def record(customer, phone, answers, when=None):
    """One Consent row per kind, yes or no, with the words shown."""
    when = when or timezone.now()
    words = wording()["versions"][answers["version"]]
    return [
        Consent.objects.create(
            customer=customer, kind=kind, granted=answers[key], phone=phone, source=Consent.Source.WEB_FORM,
            wording_version=answers["version"], wording=words[key], recorded_at=when,
        )
        for key, kind in KINDS.items()
    ]
