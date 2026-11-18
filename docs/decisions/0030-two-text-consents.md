---
id: 30
title: "Two separate text consents: appointment and follow-up"
summary: "The booking form carries two unchecked consent checkboxes, one for appointment texts and one for follow-up texts."
date: 2026-10-07
area: texting
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-11-18
supersedes: []
superseded_by: [docs/decisions/0108-one-text-consent.md]
related: [docs/reference/text-messages.md]
---

# 0030: Two separate text consents: appointment and follow-up

**Status:** superseded by [0108](0108-one-text-consent.md): one consent, for texts about a booked job including one review request, from 2026-11-18 · **Date:** 2026-10-07 · **Area:** texting

## Context

Review requests and follow-ups are closer to marketing than reminders, and carriers require clear, separate, never pre-checked consent.

## Decision

Two checkboxes, both unchecked and optional, next to the submit button, linking to the Privacy Policy and Text Message Terms. Phone bookings ask verbally and record the answer. Each consent is stored with date, source and wording version.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Follow-up texts go only to customers with follow-up consent.
