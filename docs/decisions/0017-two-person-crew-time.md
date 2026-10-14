---
id: 17
title: "Two people take 60% of the one-person time"
summary: "Matrix hours are one-person hours; a two-person crew takes 60% of them, rounded to 15 minutes; crews are one or two people."
date: 2026-10-07
area: crew
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, data/pricing-rules.yaml]
---

# 0017: Two people take 60% of the one-person time

**Status:** accepted · **Date:** 2026-10-07 · **Area:** crew

## Context

The owner measured how much faster two people finish.

## Decision

Store the 60% factor and 15-minute rounding as rules. Larger crews are not planned.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

A 6.5-hour Full Detail becomes 4 hours with two people.
