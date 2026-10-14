---
id: 47
title: "Money is stored as exact decimals, never floating point"
summary: "Every amount of money is stored and calculated as an exact decimal, never as a floating-point number, so prices, tax and totals are exact to the cent."
date: 2026-10-14
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, docs/reference/sales-tax.md, docs/architecture/data-model.md]
---

# 0047: Money is stored as exact decimals, never floating point

**Status:** accepted · **Date:** 2026-10-14 · **Area:** pricing

## Context

Prices, percentage adjustments, sales tax, tips, fees and refunds are all calculated by the server and exported to GnuCash, where they must match bank deposits to the cent. Floating-point numbers cannot hold most cent values exactly: 0.10 + 0.20 is not exactly 0.30, and such errors can change a rounded total.

## Decision

- Every amount of money is stored in PostgreSQL as `numeric` through Django's `DecimalField`, in dollars with two decimal places.
- Every calculation uses Python's `Decimal`, with rounding done explicitly at the step the rules in [pricing.md](../reference/pricing.md) and [sales-tax.md](../reference/sales-tax.md) name.
- Percentages and rates, such as a tax rate, are also stored as decimals.
- A floating-point value never holds money, in the database, in code, or in what the server sends out.

## Alternatives considered

- **Floating-point numbers.** Inexact for cents; small errors surface as a total a cent off.
- **Whole cents as integers.** Also exact, but every display, import and percentage step would need converting, and Django's decimal fields already do the job.

## Consequences

Totals, tax and GnuCash exports agree to the cent. The public API will send amounts as text such as `"185.00"`, so the website's JavaScript never turns them into floating-point numbers. Tests compare amounts as decimals.
