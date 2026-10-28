---
id: 29
title: "Vehicle data from EPA FuelEconomy.gov and NHTSA vPIC"
summary: "Free government data sets the vehicle class from year, make and model, with override rules and an owner review queue; RockAuto is not used."
date: 2026-10-07
area: vehicles
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: [docs/decisions/0082-size-based-vehicle-classes.md]
related: [docs/reference/vehicle-classification.md]
---

# 0029: Vehicle data from EPA FuelEconomy.gov and NHTSA vPIC

**Status:** superseded by [0082](0082-size-based-vehicle-classes.md) for the EPA size class as the first guess at a class, applied by `apply_size_classes` ([0083](0083-applying-the-size-based-classes.md)); the data sources stand · **Date:** 2026-10-07 · **Area:** vehicles

## Context

Customers should pick a vehicle, not a category. A free, reliable source of makes, models and sizes was needed.

## Decision

EPA size classes give a first guess, override rules fix mismatches, NHTSA fills gaps such as heavy trucks, and a monthly refresh queues ambiguous models for the owner.

## Alternatives considered

- **RockAuto.** No public API; scraping may breach its terms and meets CAPTCHA blocks.

## Consequences

Optional third rows have no clean source, so per-model flags are seeded and reviewed.
