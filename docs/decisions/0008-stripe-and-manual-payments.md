---
id: 8
title: "Stripe for cards and Cash App Pay; a \"paid\" button for the rest; no deposit"
summary: "Cards and Cash App Pay go through Stripe and mark themselves paid; cash, Venmo, PayPal and Bitcoin use a one-tap \"paid\" button; payment is due at service."
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

# 0008: Stripe for cards and Cash App Pay; a "paid" button for the rest; no deposit

**Status:** accepted · **Date:** 2026-10-07 · **Area:** payments

## Context

The business takes cash, card, Venmo, PayPal, Cash App and Bitcoin, with payment due at the time of service.

## Decision

Stripe payment links (with Cash App Pay) and Tap to Pay on the Pixel. Manual methods are recorded with a "paid" button. No deposit and no card on file.

## Alternatives considered

- **Automate Venmo and PayPal now through PayPal Checkout.** Possible later; not needed for launch.

## Consequences

Card details never touch the server. The data model leaves room for a deposit later.
