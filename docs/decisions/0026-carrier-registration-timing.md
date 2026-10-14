---
id: 26
title: "Submit text registration when the new booking form is public"
summary: "Carrier registration is submitted once, for all message types, when the new booking form with its consent checkboxes is public; the number ports only after approval."
date: 2026-10-08
area: texting
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/text-messages.md]
---

# 0026: Submit text registration when the new booking form is public

**Status:** accepted · **Date:** 2026-10-08 · **Area:** texting

## Context

The only form collecting phone numbers today is Setmore's, which cannot carry compliant consent wording. Quo blocks texts from unregistered numbers, and registration does not move with a ported number.

## Decision

Wait. Submit in Phase 3 once the booking form is public, then port (423) 380-9120 to Quo after approval. Setmore keeps sending its own reminders until launch.

## Alternatives considered

- **Register now for appointment texts only.** Reviewers check the website, and Setmore's opt-in is not compliant, so a rejection was likely.
- **Port the number now (weighed 2026-10-13).** Outbound texts from the business number would be blocked until registration, possibly for months.

## Consequences

Reaffirmed by the owner on 2026-10-13. Automated texts cannot start before Phase 3.
