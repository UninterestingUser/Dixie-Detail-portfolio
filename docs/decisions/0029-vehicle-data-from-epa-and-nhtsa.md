---
id: 29
title: "Vehicle data from EPA FuelEconomy.gov and NHTSA vPIC"
summary: "Free government data sets the vehicle class from year, make and model, with override rules and an owner review queue; RockAuto is not used."
date: 2026-10-07
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/vehicle-classification.md]
---

# 0029: Vehicle data from EPA FuelEconomy.gov and NHTSA vPIC

**Status:** accepted · **Date:** 2026-10-07 · **Area:** vehicles

## Context

Customers should pick a vehicle, not a category. A free, reliable source of makes, models and sizes was needed.

## Decision

EPA size classes give a first guess, override rules fix mismatches, NHTSA fills gaps such as heavy trucks, and a monthly refresh queues ambiguous models for the owner.

## Alternatives considered

- **RockAuto.** No public API; scraping may breach its terms and meets CAPTCHA blocks.

## Consequences

Optional third rows have no clean source, so per-model flags are seeded and reviewed.
