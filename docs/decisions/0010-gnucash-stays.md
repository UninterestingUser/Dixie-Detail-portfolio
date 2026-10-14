---
id: 10
title: "GnuCash stays the general ledger, fed by an export"
summary: "The owner keeps GnuCash; the system exports balanced multi-split CSV transactions for import."
date: 2026-10-07
area: bookkeeping
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/bookkeeping-gnucash.md]
---

# 0010: GnuCash stays the general ledger, fed by an export

**Status:** accepted · **Date:** 2026-10-07 · **Area:** bookkeeping

## Context

The owner already keeps full double-entry books in GnuCash and does not want paid accounting software.

## Decision

The core app keeps the sales side and exports paid jobs, fees, payouts and refunds as GnuCash multi-split CSV for the owner to import with a saved preset.

## Alternatives considered

- **Paid accounting software.** A new cost and a new tool to learn.
- **Direct posting through GnuCash's Python bindings.** Untested; kept as an option.

## Consequences

Nothing is retyped. Expenses and some transfers stay manual in GnuCash. See decision 0035 for the account mapping.
