---
id: 24
title: "Google Maps Platform for address suggestions and drive times"
summary: "Google Maps Platform provides booking-form address suggestions and traffic-aware drive times, inside its free monthly allowance."
date: 2026-10-07
area: maps
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/integrations.md, docs/decisions/0032-address-validation-with-places.md]
---

# 0024: Google Maps Platform for address suggestions and drive times

**Status:** accepted · **Date:** 2026-10-07 · **Area:** maps

## Context

The booking form needs real addresses, and alerts need drive times with traffic.

## Decision

Use Places Autocomplete and Routes on the same Google Cloud project as the calendar service account. The billing account is approved.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

The browser key is public by design and locked to dixiedetail.com; the server key is a Bitwarden secret.
