---
id: 54
title: "Gift cards are a balance owed until used; vouchers are promotions"
summary: "Gift cards are sold as a dollar balance with sales tax included, held as a liability until spent across one or more jobs; free vouchers are promotions with a code and a dollar value."
date: 2026-10-14
area: payments
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/payments.md, docs/reference/bookkeeping-gnucash.md, data/gnucash-accounts.yaml, docs/architecture/data-model.md]
---

# 0054: Gift cards are a balance owed until used; vouchers are promotions

**Status:** accepted · **Date:** 2026-10-14 · **Area:** payments

## Context

The business sells gift cards and gives away free promotional vouchers. The Baserow history has one job paid by gift card. Selling a gift card is not a sale of detailing: the work, and the sales tax on it, happen when the card is used, possibly over several jobs. A free voucher brings in no money at all.

## Decision

**Gift cards**

- A gift card is sold as a dollar balance, with sales tax included in that amount. Each card has a code, the buyer and an optional recipient.
- The balance is money owed to the holder until it is used. It can be spent across several jobs. A card can never go below zero; when the balance does not cover a bill, the rest is paid another way.
- The one imported gift-card job stays a simple prepayment, with no card record.

**Vouchers**

- A free promotional voucher is a kind of promotion, with a code and a dollar value. It appears on a job as a promotion line and never takes more than the job's price.

**GnuCash postings**

| When | Debit | Credit |
| --- | --- | --- |
| Gift card sold | The account the buyer paid into | Liabilities:Gift Cards Outstanding, the whole amount. No sales tax |
| Gift card used on a job | Liabilities:Gift Cards Outstanding | Income:Detailing Services and Liabilities:Sales Tax Payable, as for any paid job |
| Voucher given | Nothing | Nothing |
| Voucher used on a job | Income:Discounts & Refunds, the value used | None; tax is charged on the reduced price |

## Alternatives considered

- **Treat a gift card sale as income.** Counts income and sales tax before the work is done, and again when the card is used.
- **Treat a voucher like a gift card.** Nobody paid for it, so there is no liability to record; it is a discount.

## Consequences

The owner needs a Liability account named Liabilities:Gift Cards Outstanding in GnuCash before the first export that includes a gift card. Its balance shows what the business owes on unused cards.
