---
id: 32
title: "Booking addresses validated with Google Places Autocomplete"
summary: "The address field suggests and validates real addresses as the customer types, like a Shopify checkout, using Google Places Autocomplete (New)."
date: 2026-10-10
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/booking-flow.md]
---

# 0032: Booking addresses validated with Google Places Autocomplete

**Status:** accepted · **Date:** 2026-10-10 · **Area:** booking

## Context

The owner required addresses checked against a real address database, with no separate check button.

## Decision

Places Autocomplete restricted to US addresses and biased to the service area. A chosen suggestion supplies verified parts and coordinates for the service-area check and tax lookup. Address Validation API may be added later for unit numbers.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Expected to stay inside Google's free monthly usage.
