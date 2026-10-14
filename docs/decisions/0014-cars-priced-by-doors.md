---
id: 14
title: "Cars are priced by doors, not seats"
summary: "For Coupes & Sedans, two doors takes the 1-row price and four doors the 2-row price."
date: 2026-10-07
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md]
---

# 0014: Cars are priced by doors, not seats

**Status:** accepted · **Date:** 2026-10-07 · **Area:** pricing

## Context

The price matrix's size column was labelled seat rows, but the owner prices cars by door count.

## Decision

Use doors for cars, cab style for pickups (regular = 1, extended or crew = 2), and seat rows for crossovers and SUVs.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Hatchbacks follow the door count; convertibles are two-door. The vehicle data must carry door counts.
