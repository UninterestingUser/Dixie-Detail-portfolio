---
id: 25
title: "Sales tax added on top at the service address's rate"
summary: "Sales tax is added on top of the price at the rate for the customer's service address, tracked by jurisdiction until remitted."
date: 2026-10-07
area: tax
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/sales-tax.md]
---

# 0025: Sales tax added on top at the service address's rate

**Status:** accepted · **Date:** 2026-10-07 · **Area:** tax

## Context

Mobile services are performed at the customer's address; the state's guidance for this case could not be confirmed.

## Decision

Use the service address's rate from the state's boundary data. Keep the sourcing rule as a single setting in case the accountant advises the business-location rate.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Every invoice stores state tax, local tax and jurisdiction. See decision 0037 for out-of-area addresses.
