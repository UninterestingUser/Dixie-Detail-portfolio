---
id: 35
title: "GnuCash account mapping and booked-when-paid"
summary: "Each payment method posts to its own asset account; income splits per line; tips and sales tax have their own accounts; jobs are booked when paid."
date: 2026-10-11
area: bookkeeping
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/bookkeeping-gnucash.md, data/gnucash-accounts.yaml]
---

# 0035: GnuCash account mapping and booked-when-paid

**Status:** accepted · **Date:** 2026-10-11 · **Area:** bookkeeping

## Context

The owner supplied and cleaned up the GnuCash chart of accounts.

## Decision

Use the mapping in `data/gnucash-accounts.yaml`. Receivables stay in the control app; the export never posts to Accounts Receivable. Sales Tax Payable stays a plain Liability.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Some fees and transfers stay manual. Bitcoin waits for Phase 7.
