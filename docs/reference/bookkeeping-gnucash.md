---
title: Bookkeeping with GnuCash
summary: How paid jobs, fees, payouts and refunds become balanced GnuCash transactions, which accounts each event posts to, and the CSV layout the owner imports.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-17
tags: [bookkeeping, gnucash, accounting, export]
related: [data/gnucash-accounts.yaml, docs/reference/payments.md, docs/reference/sales-tax.md, docs/decisions/0010-gnucash-stays.md, docs/decisions/0035-gnucash-account-mapping.md, docs/decisions/0054-gift-cards-and-vouchers.md]
---

# Bookkeeping with GnuCash

GnuCash stays the general ledger. The system keeps the sales side and hands GnuCash balanced double-entry transactions to import, so nothing is retyped. The account mapping was settled with the owner on 2026-10-11; the export is built in Phase 6. Account names are in [data/gnucash-accounts.yaml](../../data/gnucash-accounts.yaml).

## How transactions are produced

1. Every paid job produces one transaction, dated the day it was paid. The payment account is debited for the total. Income:Detailing Services is credited once per line (service, condition and each add-on, named in the memo), Income:Tips takes any tip, and Liabilities:Sales Tax Payable takes the tax.
2. Jobs finished but not yet paid stay in the control app's open balances. The export never posts to Accounts Receivable; jobs are booked when paid.
3. Stripe fees and payouts produce their own transactions, so the Stripe balance reconciles to the bank deposits.
4. The control app exports any date range as one file in GnuCash's multi-split CSV layout, using full account names.
5. The owner imports it in GnuCash with a saved preset. GnuCash's importer supports multi-split files, saved settings and duplicate matching.
6. Payments and helper payouts imported from Baserow are already in the books. They belong to the export batch "Already in GnuCash: Baserow import", so the export never sends them ([decision 0066](../decisions/0066-imported-payments-already-in-the-books.md)).

## Account mapping

| When | Debit | Credit |
| --- | --- | --- |
| Paid by card or Cash App Pay (both settle in Stripe) | Assets:Current Assets:Stripe | Income:Detailing Services, Income:Tips, Liabilities:Sales Tax Payable |
| Paid by Venmo | Assets:Current Assets:Venmo | The same three |
| Paid by PayPal | Assets:Current Assets:PayPal | The same three |
| Paid in cash | Assets:Current Assets:Petty Cash | The same three |
| Paid straight to the owner's $cashtag | Assets:Current Assets:Cash.App | The same three |
| Paid in bitcoin | Left out of the export and listed for manual entry until Phase 7 adds an account | The same three |
| Paid by check (owner only) | Assets:Current Assets:Checking Account, as a direct deposit | The same three |
| Paid in a trade (owner only) | Left out of the export and listed for manual entry, with the goods received and their value | The same three |
| Gift card sold | The account the buyer paid into | Liabilities:Gift Cards Outstanding, the whole amount, with no sales tax |
| Paid with a gift card's balance | Liabilities:Gift Cards Outstanding | The same three as any paid job |
| The imported gift-card prepayment (no card record) | Listed for manual entry | The same three |
| Free voucher given | Nothing is posted | Nothing |
| Free voucher used on a job | Income:Discounts & Refunds, the value used, as an extra split | None; tax is charged on the reduced price |
| Promotion or discount on a job | Income:Discounts & Refunds, as an extra split | None; tax is charged on the discounted price |
| Stripe fee on a payment | Expenses:Fees:Payment Processing Fees | Assets:Current Assets:Stripe |
| Stripe payout to the bank | Assets:Current Assets:Checking Account | Assets:Current Assets:Stripe |
| Pay to a family helper | Expenses:Professional Services | The account the pay came from |
| Pay to an employee (planned) | No account yet; wages and payroll are a later decision | The account the pay came from |
| Refund | Income:Discounts & Refunds, plus Liabilities:Sales Tax Payable for the tax refunded | The account it was paid from |

Helper pay posts by the helper's pay type, copied onto each payout, not to one fixed account. Family helpers are paid as professional services on the advice of the owner's accountant; that is not a rule for every helper. The owner confirmed the Expenses:Professional Services account on 2026-10-17; how family helpers are paid will be revisited when their help becomes regular. See [decision 0053](../decisions/0053-check-and-trade-owner-only.md).

Sales Tax Payable and Loans are Liability-type accounts in the owner's chart. Gift Cards Outstanding is a Liability account, created in GnuCash on 2026-10-14; its balance is what the business owes on unused cards (decision 0054). Sales Tax Payable stays a plain Liability, not Accounts Payable.

## What the owner keeps entering by hand

Venmo, PayPal and Cash App fees and transfers from each statement; payments in bitcoin and trades from the export's manual-entry list; cash moved from Petty Cash to Checking; expenses; and sales tax payments (Sales Tax Payable to Checking, using the app's tax report).

## The CSV layout, with an example

A row with a date starts a transaction; the blank-date rows under it are its other splits. Positive amounts are debits. This example is a card payment for the RAV4 job used in the mockups, with a $40 tip:

```csv
Date,Num,Description,Account,Amount,Memo
2026-10-13,J-1042,Full Detail · 2019 Toyota RAV4,Assets:Current Assets:Stripe,429.61,Card
,,,Income:Detailing Services,-250.00,Full Detail
,,,Income:Detailing Services,-25.00,Condition: needs attention (+10%)
,,,Income:Detailing Services,-80.00,Seat Extraction
,,,Income:Tips,-40.00,Tip
,,,Liabilities:Sales Tax Payable,-34.61,Cleveland 9.75%
```

## Options kept open

GnuCash has Python bindings that could post entries with no import step (untested). The same export could also feed a plain-text ledger such as Beancount if the owner ever moves off GnuCash.
