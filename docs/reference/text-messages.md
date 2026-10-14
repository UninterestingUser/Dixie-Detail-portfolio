---
title: Text messages and consent
summary: Which automated texts the system sends, the two kinds of consent each one needs, the exact consent wording, automatic STOP and HELP replies, and the carrier registration plan.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [texting, sms, consent, compliance, quo]
related: [data/message-templates.yaml, docs/decisions/0026-carrier-registration-timing.md, docs/decisions/0030-two-text-consents.md, docs/decisions/0007-quo-phone-and-texts.md]
---

# Text messages and consent

The business uses Quo (formerly OpenPhone) for one number that handles calls, the owner's own texts and the automated texts. Automated texts are built in Phase 4. US carriers will not deliver automated texts until the business and its message types are registered, so consent and registration rules come first. This page is not legal advice; the consent wording deserves a quick professional check.

## Registration status (2026-10-13)

- The Quo account is open on a new number on the Starter plan, which includes the API and webhooks.
- Carrier registration has **not** been submitted. It will be submitted once, for every message type, as soon as the new website's booking form with its two consent checkboxes is public (Phase 3).
- The business number (423) 380-9120 stays with its current VoIP provider. It is ported to Quo only after registration is approved, because Quo blocks texts from unregistered numbers and registration does not carry over from the old provider. The owner weighed porting early on 2026-10-13 and chose to wait.
- Setmore keeps sending its own reminders until launch.

Quo's guide says most approvals take 24 to 48 hours and some 20 days or more. Fees: $19.50 once, $1.50 a month, $15 to resubmit after a rejection.

## The two kinds of consent

The booking form has two separate checkboxes, both unchecked by default, neither required to submit, placed next to the submit button.

| Consent | Covers |
| --- | --- |
| Appointment texts | Confirmations, reminders, arrival updates, payment links, receipts and replies about the job |
| Follow-up texts | Review requests, service-due reminders and occasional offers |

Each consent is recorded with its date, source (web form or phone) and the wording version. Follow-up texts go only to customers with follow-up consent. Every message starts with "Dixie Detail:" and carries opt-out wording where required.

## Consent wording

**Checkbox 1, appointment texts:**

> I agree to receive text messages from Dixie Detail about my appointment at the number I provided, including confirmations, reminders, arrival updates, payment links and receipts. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. See our Privacy Policy and Text Message Terms.

**Checkbox 2, follow-up texts:**

> I also agree to receive occasional follow-up text messages from Dixie Detail, such as review requests, service reminders and offers. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase.

"Privacy Policy" and "Text Message Terms" link to the two published pages.

**On the phone,** the owner asks this and records the answer in the customer's record:

> Is it okay if we text you at this number with your appointment confirmation and reminders? You can reply STOP at any time to end them.

## Automatic replies

| When a customer texts | Reply |
| --- | --- |
| STOP | Dixie Detail: You are unsubscribed and will receive no more texts from us. Reply START to resubscribe. |
| HELP | Dixie Detail: For help, call or text (423) 380-9120 or email [business email]. Message and data rates may apply. Reply STOP to opt out. |
| START | Dixie Detail: You are resubscribed to appointment texts. Message frequency varies. Message and data rates may apply. Reply STOP to opt out, HELP for help. |

## The automated messages

Six automated texts, each with a template the owner edits in the control app. Seed wording and the consent each needs are in [data/message-templates.yaml](../../data/message-templates.yaml).

1. Booking confirmation, sent immediately.
2. Reminder with preparation details: water, power and where to park the vehicle.
3. "On my way", sent with one tap from the time-to-leave alert.
4. Payment link at completion, then a receipt.
5. Review request with the Google review link (follow-up consent).
6. Follow-up when the next detail is due (follow-up consent).

## What registration needs

- The legal name exactly as on the EIN letter, including "LLC", and the address the IRS has on file.
- A live website showing business details and contact information.
- Consent wording next to the submit button of every form that collects a phone number, linking to the privacy policy.
- A point of contact using the owner's personal cell number, not a VoIP number, and an email at the business domain if possible.
- Every message type to be sent: appointment, customer care, payment, review requests, follow-ups and offers.

Draft answers for the registration form ("How you use text messaging", "How customers opt in") are in the doc "Dixie Detail: Privacy Policy, Text Terms and Quo Registration Answers" (a private document).

## Published policy pages

- Privacy Policy: https://dixiedetail.com/privacy-policy/
- Text Message Terms: https://dixiedetail.com/sms-terms/

Both are linked in the footer and open to search engines. The new website must carry both pages at the same addresses, copied from the live text.
