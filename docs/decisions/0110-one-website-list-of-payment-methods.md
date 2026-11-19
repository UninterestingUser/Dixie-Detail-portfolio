---
id: 110
title: "The website offers one list of payment methods, one entry per method, with one Cash App"
summary: "Customers pick from Cash, Card, Venmo, PayPal, Cash App and Bitcoin, as listed in data/business.yaml; Cash App is saved as Cash App Pay, and its two routes stay for recording payments."
date: 2026-11-19
area: payments
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-19
supersedes: []
superseded_by: []
related: [docs/reference/payments.md, docs/reference/public-api.md, docs/reference/booking-flow.md, data/business.yaml, docs/decisions/0053-check-and-trade-owner-only.md]
---

# 0110: The website offers one list of payment methods, one entry per method, with one Cash App

**Status:** accepted · **Date:** 2026-11-19 · **Area:** payments

## Context

The booking form listed every payment method the control app records except check, trade and gift card. That put Cash App on the page twice, as "Cash App Pay" and "Cash App to the owner's $cashtag": the two ways a Cash App payment reaches the owner, which matter for recording a payment but mean nothing to a customer choosing how they'd like to pay. The owner asked for one list, one entry per method (2026-11-19, carried from Task C).

## Decision

- **The website's list is `payment_methods_accepted` in `data/business.yaml`, in its order:** Cash, Card, Venmo, PayPal, Cash App and Bitcoin. `billing/methods.py` maps each name to the website's value and label and the method saved, and a name with no mapping is an error, so a method is never dropped from the website by accident.
- **A Cash App choice (`cash_app`) is saved as Cash App Pay,** the route the payment link offers. The booking summary and the control app name it as the customer saw it, "Cash App". The owner records the payment by the route it actually took.
- **The two Cash App routes stay in the control app** for recording payments, unchanged.
- **Check and trade stay owner-only** ([decision 0053](0053-check-and-trade-owner-only.md)), and a gift card is never chosen at booking.
- **An older page's values are still taken:** `cash_app_pay` and `cash_app_direct`, as in a request held while the server was offline, are saved as themselves.

## Alternatives considered

- **A new "Cash App, route not known" method.** It would show up among the methods for recording payments too, where a route must be known.
- **Keeping both Cash App entries with plainer names.** Still asks the customer a question only the owner needs answered.

## Consequences

Adding a payment method to the website means adding it to `payment_methods_accepted` and to `WEBSITE_CHOICES` in `app/billing/methods.py`.
