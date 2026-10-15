---
id: 55
title: "Percentage promotions round to the nearest cent"
summary: "A percentage promotion's discount is rounded to the nearest $0.01, with an exact half cent rounded up, unlike the condition adjustment, which rounds to the whole dollar."
date: 2026-10-14
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, data/pricing-rules.yaml, docs/decisions/0047-money-as-exact-decimals.md]
---

# 0055: Percentage promotions round to the nearest cent

**Status:** accepted · **Date:** 2026-10-14 · **Area:** pricing

## Context

A percentage off can produce fractions of a cent: 15% off $133.33 is $19.9995. The pricing rules said the condition adjustment rounds to the whole dollar, but said nothing about promotions, so the data model refused to apply a percentage promotion until a rule was set.

## Decision

A percentage promotion's discount is rounded to the nearest $0.01. An exact half cent rounds up, so 12.5% off $0.20 ($0.025) is $0.03. The owner set the nearest-cent rule on 2026-10-14; rounding an exact half cent up is the usual rule for money.

## Alternatives considered

- **Round to the whole dollar, like the condition adjustment.** Not chosen by the owner; a promotion is a discount the customer sees to the cent.
- **Round half to even (banker's rounding).** Less familiar to customers and the owner checking a bill by hand.

## Consequences

Percentage promotions can now be applied. The discount is rounded once, on the amount it applies to, before sales tax is added. The condition adjustment still rounds to the whole dollar.
