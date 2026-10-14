---
id: 12
title: "Maintenance plans are priced as a share of Full Detail"
summary: "Quarterly Maintenance is 80% and Monthly Maintenance 50% of the Full Detail price, stored as a rule."
date: 2026-10-07
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, data/pricing-rules.yaml]
---

# 0012: Maintenance plans are priced as a share of Full Detail

**Status:** accepted · **Date:** 2026-10-07 · **Area:** pricing

## Context

The owner's maintenance prices followed Full Detail by fixed ratios.

## Decision

Store the ratios as rules, not as separate prices. Both plans take the Full Detail hours and are booked by the owner only.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Changing a Full Detail price moves both maintenance prices.
