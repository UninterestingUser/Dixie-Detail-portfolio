---
id: 7
title: "Quo for calls and texts, porting the business number after registration"
summary: "Quo provides one number for calls, the owner's texts and automated texts; (423) 380-9120 ports to Quo after carrier registration is approved."
date: 2026-10-07
area: phone
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/text-messages.md, docs/decisions/0026-carrier-registration-timing.md]
---

# 0007: Quo for calls and texts, porting the business number after registration

**Status:** accepted · **Date:** 2026-10-07 · **Area:** phone

## Context

A customer who replies to an automated reminder should reach the owner in the same phone app.

## Decision

Use Quo (formerly OpenPhone) on the Starter plan, which includes the API and webhooks. Port the current VoIP number in at no charge once carrier registration clears.

## Alternatives considered

- **Twilio.** Cheaper pure API, but no phone app, so calls would need a second service.

## Consequences

One number on the website and Google profile, unchanged. Automated texts depend on carrier registration; see decision 0026.
