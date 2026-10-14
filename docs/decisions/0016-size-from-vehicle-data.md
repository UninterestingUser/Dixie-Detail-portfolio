---
id: 16
title: "Derive the size variant from vehicle data; ask only when needed"
summary: "The system sets doors, cab or seat rows from the vehicle data and asks the customer only when the data cannot settle it."
date: 2026-10-07
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/vehicle-classification.md]
---

# 0016: Derive the size variant from vehicle data; ask only when needed

**Status:** accepted · **Date:** 2026-10-07 · **Area:** booking

## Context

Customers should not have to guess their category.

## Decision

Each vehicle model stores its size rule (1, 2, 3 or "ask"). Questions appear only for cars sold both ways, pickups with several cab styles, and optional third rows.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Per-model flags are seeded, then reviewed by the owner, and corrected on jobs.
