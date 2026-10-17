---
id: 59
title: "The quoted price is the price of record"
summary: "Only the server's pricing engine computes prices; a server-issued quote becomes the appointment's line snapshot, and the owner is alerted to any price change not of the owner's making."
date: 2026-10-17
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, docs/reference/booking-flow.md, docs/reference/sales-tax.md, docs/reference/pricebook-changes.md, data/pricing-rules.yaml, docs/decisions/0033-pricebook-versions-and-line-snapshots.md]
---

# 0059: The quoted price is the price of record

**Status:** accepted · **Date:** 2026-10-17 · **Area:** pricing

## Context

What gives the owner confidence in prices is that the website and the control app show the same price from one source, and that the owner hears about any change between booking and the appointment. Decision 0033 already copies lines onto each appointment, but nothing said where those lines come from, or what happens when sales tax or an offline booking changes a number.

## Decision

- **One source.** Only the server's pricing engine computes prices. The website's estimate card and the control app display its results and do no arithmetic of their own.
- **The price shown is the price booked.** The server issues a quote record: its inputs, lines, totals, pricebook version, tax rate, service time and time on site. The website books with a reference to the quote, never a price sent from the browser, and the quote's lines become the appointment's line snapshot (decision 0033). The control app never re-prices a booked job. The quote record is built in Phase 1 Step 3; the website uses it in Phase 3.
- **The owner is notified of any change.** If a booked job's price changes for any reason other than a choice the owner made, such as a sales tax rate change, the owner gets a push alert and the control app shows the booked total beside the new one. The owner's own edits need a reason and are logged.
- **Website offline:** the "request a time" form shows prices from the last published pricebook. When the server returns, it prices each request, and the owner is notified if one differs from what the customer saw.
- **Sales tax:** a job is taxed at the rate on the day of service. If a rate changes after booking, the new rate applies and the owner is notified. The price before tax never changes.

## Alternatives considered

- **Customer re-confirmation, quote-number texts, nightly price checks or end-to-end booking tests.** Not added; each costs effort and messages without adding confidence the alerts and the normal test suite don't already give.
- **Let the website compute the estimate.** Two price calculations would eventually disagree.

## Consequences

The booking API takes a quote reference instead of a price. Tests of the pricing engine cover the numbers the customer sees. Repricing on a pricebook publish still follows `docs/reference/pricebook-changes.md`, which is an owner's choice and so raises no alert.
