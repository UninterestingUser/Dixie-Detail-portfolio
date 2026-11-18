"""The text consent wording, by version, from data/consent-wording.yaml.
The website shows the current version and sends it back with the answer;
the server records it with the words of that version from the file, never
words from the browser (text-messages.md).

There is one consent from version 2026-11-18 (decision 0108): appointment
texts, which also cover the review request after the service. An answer
sent with version 2026-10-13, such as an offline request held while the
server was down, may still carry the old follow-up answer; it is accepted
and not recorded, since follow-up consent is no longer collected.
"""

from functools import cache

import yaml
from django.conf import settings
from django.utils import timezone

from customers.models import Consent

from . import validate
from .http import bad_request


@cache
def wording():
    return yaml.safe_load((settings.DATA_DIR / "consent-wording.yaml").read_text())


def current():
    data = wording()
    version = data["current"]
    return {"version": version, "appointment": data["versions"][version]["appointment"], "links": data["links"]}


def parse(value, field="consents"):
    """{"version": ..., "appointment": bool}, checked. A follow_up answer
    from the older wording is accepted and left out."""
    validate.only(value, ["version", "appointment"], ["follow_up"], field=field)
    version = value["version"]
    if not isinstance(version, str) or version not in wording()["versions"]:
        raise bad_request(f"{field}.version", "The consent wording has changed. Please reload the page.")
    if "follow_up" in value:
        validate.boolean(value["follow_up"], f"{field}.follow_up")
    return {"version": version, "appointment": validate.boolean(value["appointment"], f"{field}.appointment")}


def record(customer, phone, answers, when=None):
    """One appointment-text Consent row, yes or no, with the words shown."""
    when = when or timezone.now()
    words = wording()["versions"][answers["version"]]
    return [
        Consent.objects.create(
            customer=customer, kind=Consent.Kind.APPOINTMENT, granted=answers["appointment"], phone=phone,
            source=Consent.Source.WEB_FORM, wording_version=answers["version"], wording=words["appointment"], recorded_at=when,
        )
    ]
