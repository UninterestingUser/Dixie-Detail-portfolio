---
id: 108
title: "One text consent, for texts about a booked job, including one review request"
summary: "The forms ask one consent question, recorded as appointment-text consent, which now also covers one review request after the service; follow-up consent is no longer collected, and no promotional texts are sent."
date: 2026-11-18
area: texting
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-18
supersedes: [docs/decisions/0030-two-text-consents.md]
superseded_by: []
related: [docs/reference/text-messages.md, data/consent-wording.yaml, data/message-templates.yaml, docs/reference/public-api.md, docs/reference/booking-flow.md, docs/decisions/0026-carrier-registration-timing.md, docs/decisions/0030-two-text-consents.md]
---

# 0108: One text consent, for texts about a booked job, including one review request

**Status:** accepted · **Date:** 2026-11-18 · **Area:** texting

## Context

Decision 0030 put two unchecked checkboxes on every form: appointment texts, and follow-up texts for review requests, service-due reminders and offers. Before carrier registration, the owner chose on 2026-11-18 to send only texts about a booked job. One review request after the service is part of that. There are no promotional texts for now.

## Decision

- **The booking, quote request and offline request forms ask one consent question.** It is one unchecked checkbox, not required, next to the submit button. The wording is version 2026-11-18 in `data/consent-wording.yaml`.
- **The answer is recorded as appointment-text consent,** which now also covers the one review request after the service.
- **The follow-up consent type stays in the data,** for the answers already recorded, but it is no longer collected. An answer sent with version 2026-10-13, such as an offline request held before the change, may still carry a follow-up answer. The server accepts it and records only the appointment answer.
- **No promotional or service-due texts.** The "time for your next detail" template is dropped. A separate marketing consent may come back with Phase 6.
- **The phone wording and the Quo registration answers** in [text-messages.md](../reference/text-messages.md) say the same: texts are about a booked job only, with message types appointment confirmations and reminders, customer care, payment and receipt notices, and review requests.

## Alternatives considered

- **Keep two checkboxes.** A second box for a review request alone asks the customer twice about one job, and promotional texts aren't planned.
- **Drop the review request.** Reviews matter to a local business, and one request after a job the customer booked is within what they agreed to.

## Consequences

- The registration lists no marketing use case. Adding marketing later means a new consent and a registration update.
- The public API's consent answer has one field, `appointment`.
