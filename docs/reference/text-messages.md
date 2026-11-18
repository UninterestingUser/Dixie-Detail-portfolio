---
title: Text messages and consent
summary: Which automated texts the system sends, the one consent they need, the exact consent wording, automatic STOP and HELP replies, the carrier registration plan and its answers.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-11-18
tags: [texting, sms, consent, compliance, quo]
related: [data/consent-wording.yaml, docs/reference/public-api.md, data/message-templates.yaml, docs/decisions/0026-carrier-registration-timing.md, docs/decisions/0108-one-text-consent.md, docs/decisions/0030-two-text-consents.md, docs/decisions/0007-quo-phone-and-texts.md]
---

# Text messages and consent

The business uses Quo (formerly OpenPhone) for one number that handles calls, the owner's own texts and the automated texts. Automated texts are built in Phase 4. US carriers will not deliver automated texts until the business and its message types are registered, so consent and registration rules come first. This page is not legal advice; the consent wording deserves a quick professional check.

## Registration status (2026-10-13)

- The Quo account is open on a new number on the Starter plan, which includes the API and webhooks.
- Carrier registration has **not** been submitted. It will be submitted once, for every message type, as soon as the new website's booking form with its consent checkbox is public (Phase 3).
- The business number (423) 380-9120 stays with its current VoIP provider. It is ported to Quo only after registration is approved, because Quo blocks texts from unregistered numbers and registration does not carry over from the old provider. The owner weighed porting early on 2026-10-13 and chose to wait.
- Setmore keeps sending its own reminders until launch.

Quo's guide says most approvals take 24 to 48 hours and some 20 days or more. Fees: $19.50 once, $1.50 a month, $15 to resubmit after a rejection.

## One consent: texts about a booked job

Every text is about a job the customer booked ([decision 0108](../decisions/0108-one-text-consent.md)). The booking, quote request and offline request forms have one checkbox, unchecked by default, not required to submit, placed next to the submit button. The answer is recorded as appointment-text consent.

| Consent | Covers |
| --- | --- |
| Appointment texts | Confirmations, reminders, arrival updates, payment links, receipts, replies about the job, and one review request after the service |

There are no promotional texts for now. A separate marketing consent may come back with Phase 6. Until 2026-11-18 the forms had a second checkbox, for follow-up texts ([decision 0030](../decisions/0030-two-text-consents.md)); the answers already recorded keep that kind, but it is no longer collected.

Each consent is recorded with its date, source (web form or phone) and the wording version. An answer from the website is also recorded with the exact words shown: the wording lives in [data/consent-wording.yaml](../../data/consent-wording.yaml) by version, the public API serves the current version to the form, and the server records the words of the version sent back, never words from the browser ([public-api.md](public-api.md#consent-is-recorded-with-its-exact-wording)). A wording change is a new version in that file. Every message starts with "Dixie Detail:" and carries opt-out wording where required.

## Consent wording

The wording below is version 2026-11-18, the current version in [data/consent-wording.yaml](../../data/consent-wording.yaml); the file is the source the website and the server use.

**The checkbox:**

> I agree to receive text messages from Dixie Detail about my appointment at the number I provided, including confirmations, reminders, arrival updates, payment links, receipts and a review request after the service. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. See our Privacy Policy and Text Message Terms.

"Privacy Policy" and "Text Message Terms" link to the two published pages.

**On the phone,** the owner asks this and records the answer in the customer's record:

> Is it okay if we text you at this number about your appointment, like confirmations, reminders and a review request afterward? You can reply STOP at any time.

## Automatic replies

| When a customer texts | Reply |
| --- | --- |
| STOP | Dixie Detail: You are unsubscribed and will receive no more texts from us. Reply START to resubscribe. |
| HELP | Dixie Detail: For help, call or text (423) 380-9120 or email [business email]. Message and data rates may apply. Reply STOP to opt out. |
| START | Dixie Detail: You are resubscribed to appointment texts. Message frequency varies. Message and data rates may apply. Reply STOP to opt out, HELP for help. |

## The automated messages

Five automated texts, each with a template the owner edits in the control app. Every one needs appointment-text consent. Seed wording is in [data/message-templates.yaml](../../data/message-templates.yaml).

1. Booking confirmation, sent immediately.
2. Reminder with preparation details: water, power and where to park the vehicle.
3. "On my way", sent with one tap from the time-to-leave alert.
4. Payment link at completion, then a receipt.
5. One review request with the Google review link, after the service.

There is no "time for your next detail" text and no promotional text.

## What registration needs

- The legal name exactly as on the EIN letter, including "LLC", and the address the IRS has on file.
- A live website showing business details and contact information.
- Consent wording next to the submit button of every form that collects a phone number, linking to the privacy policy.
- A point of contact using the owner's personal cell number, not a VoIP number, and an email at the business domain if possible.
- The message types to be sent, below. No promotional type.

## Quo registration answers

The answers for the registration form, as of 2026-11-18 ([decision 0108](../decisions/0108-one-text-consent.md)). They replace the earlier drafts in the doc "Dixie Detail: Privacy Policy, Text Terms and Quo Registration Answers".

**How you use text messaging:**

> Dixie Detail LLC is a mobile car detailing business in southeast Tennessee. We text customers who book a detailing appointment and agree to receive texts. Messages include booking confirmations, appointment reminders with preparation details, arrival updates on the day of service, payment links and receipts, replies to customer questions, and one review request after the service. We do not send marketing or promotional texts. Customers can reply STOP at any time to opt out.

**How customers opt in:**

> Customers opt in on our website when they book an appointment or request a quote. The form has one unchecked checkbox next to the submit button stating that they agree to receive text messages from Dixie Detail about their appointment, including confirmations, reminders, arrival updates, payment links, receipts and a review request after the service; that message frequency varies; that message and data rates may apply; and that they can reply STOP to opt out or HELP for help, with links to our Privacy Policy and Text Message Terms. Checking the box is not required to book. Customers who book by phone are asked for verbal consent, which we record in the customer record. Consent is not a condition of purchase.

**Message types to select:** appointment confirmations and reminders, customer care, payment and receipt notices, and review requests. Not promotional.

**Sample messages:** the booking confirmation, reminder, "on my way", payment link and review request templates in [data/message-templates.yaml](../../data/message-templates.yaml). The "time for your next detail" sample is dropped.

## Published policy pages

- Privacy Policy: https://dixiedetail.com/privacy-policy/
- Text Message Terms: https://dixiedetail.com/sms-terms/

Both are linked in the footer and open to search engines. The new website must carry both pages at the same addresses, copied from the live text.
