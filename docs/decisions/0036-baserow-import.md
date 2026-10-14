---
id: 36
title: "One-time import from Baserow, with Setmore filling gaps"
summary: "Customers, vehicles and appointments are imported once from Baserow before launch, with Setmore contacts filling gaps; both are then retired."
date: 2026-10-11
area: migration
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/data-migration.md]
---

# 0036: One-time import from Baserow, with Setmore filling gaps

**Status:** accepted · **Date:** 2026-10-11 · **Area:** migration

## Context

Baserow is the owner's complete record; Setmore cannot export appointments.

## Decision

Import with the agreed per-record corrections, convert UTC times to Eastern, map old service names, keep history at the price charged, and carry booked jobs over as live appointments.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Source files and corrections hold personal data and stay outside the repository.
