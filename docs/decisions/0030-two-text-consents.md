---
id: 30
title: "Two separate text consents: appointment and follow-up"
summary: "The booking form carries two unchecked consent checkboxes, one for appointment texts and one for follow-up texts."
date: 2026-10-07
area: texting
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/text-messages.md]
---

# 0030: Two separate text consents: appointment and follow-up

**Status:** accepted · **Date:** 2026-10-07 · **Area:** texting

## Context

Review requests and follow-ups are closer to marketing than reminders, and carriers require clear, separate, never pre-checked consent.

## Decision

Two checkboxes, both unchecked and optional, next to the submit button, linking to the Privacy Policy and Text Message Terms. Phone bookings ask verbally and record the answer. Each consent is stored with date, source and wording version.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Follow-up texts go only to customers with follow-up consent.
