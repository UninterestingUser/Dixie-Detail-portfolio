---
id: 9
title: "Bitcoin automation moves to its own phase after launch"
summary: "BTCPay Server and the Lightning decision wait for Phase 7 so they cannot delay launch; Bitcoin stays a manual \"paid\" method until then."
date: 2026-10-07
area: payments
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/payments.md]
---

# 0009: Bitcoin automation moves to its own phase after launch

**Status:** accepted · **Date:** 2026-10-07 · **Area:** payments

## Context

Bitcoin is an accepted method today, taken with a wallet QR code.

## Decision

Phase 7 adds BTCPay Server on the home server, the Lightning decision and automatic invoices, plus a GnuCash bitcoin account.

## Alternatives considered

- **Build it before launch.** Adds setup work on the critical path.

## Consequences

Bitcoin payments are left out of the GnuCash export and listed for manual entry until Phase 7.
