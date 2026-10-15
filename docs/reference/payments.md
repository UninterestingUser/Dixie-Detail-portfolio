---
title: Payments
summary: How each payment method is taken at the job and marked paid, and the payment rules that apply to every appointment.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-14
tags: [payments, stripe, billing]
related: [docs/reference/bookkeeping-gnucash.md, docs/decisions/0008-stripe-and-manual-payments.md, docs/decisions/0009-bitcoin-later-phase.md, docs/decisions/0053-check-and-trade-owner-only.md, docs/decisions/0054-gift-cards-and-vouchers.md, docs/architecture/data-model.md]
---

# Payments

Payment is due at the time of service, with no deposit and no card on file. The customer's preferred payment method is saved at booking. Card and Cash App payments mark themselves paid; the rest use a one-tap "paid" button on the owner's phone. These are settled rules; the payment features are built in Phase 4.

## How each method works

| Method | How it is taken at the job | How it gets marked paid |
| --- | --- | --- |
| Credit or debit card | A Stripe payment link texted to the customer, or Tap to Pay on the Pixel through the Stripe Dashboard app | Link: automatically. Tap to Pay: matched by amount and time, then confirmed with one tap |
| Cash App Pay | Inside the same Stripe payment link | Automatically |
| Cash App to the owner's $cashtag | Direct transfer | The owner taps "paid" |
| Venmo | The owner's Venmo link or QR code in the payment text | The owner taps "paid" |
| PayPal | The owner's PayPal link or QR code in the payment text | The owner taps "paid" |
| Cash | In hand | The owner taps "paid" |
| Bitcoin | The owner's wallet QR code | The owner taps "paid" until Phase 7 adds BTCPay invoices |
| Check (owner only) | Handed to the owner, by arrangement | The owner records it with the check number |
| Trade (owner only) | Goods instead of money, by arrangement | The owner records what was received and its value |

## Gift cards and vouchers

- **A gift card** is sold as a dollar balance, with sales tax included in that amount. It has a code, the buyer and, if given, the recipient. The balance is money owed until it is used, and it can be spent across several jobs.
- **Paying with a gift card** uses as much of the balance as the bill needs. A card never goes below zero: when the balance does not cover the bill, the rest is paid another way, as a second payment.
- **A free voucher** is a promotion with a code and a dollar value. It appears on the job as a promotion line, and never takes more than the job's price.
- How each posts in GnuCash is in [bookkeeping-gnucash.md](bookkeeping-gnucash.md). See [decision 0054](../decisions/0054-gift-cards-and-vouchers.md).

## Owner-only methods

Checks and trades are accepted by the owner case by case and are never offered on the website. A check posts to the business checking account in GnuCash. A trade is left out of the GnuCash export and listed for manual entry, like bitcoin. See [decision 0053](../decisions/0053-check-and-trade-owner-only.md).

## Rules for every payment

- **Totals include sales tax,** shown as its own line on the payment link and the receipt.
- **Tips** are recorded separately and are not taxed. When a customer pays less than the total, the shortfall is recorded as a negative tip, as the Baserow history does, so the job's lines still show the full price.
- **Card details never touch the server.** Stripe handles them.
- **Prepayments** are recorded as payments before the job, so the appointment shows as already paid. The one imported gift-card job is such a prepayment.
- **A job paid two ways,** such as part cash and part check, has one payment for each method.
- **A job given as a gift** carries a "no charge" line, with a reason, that brings its total to zero. It has no payment.
- **A final price that differs from the list price** is an on-site adjustment line with a reason. The list price stays on the job's lines.
- **Unpaid finished jobs** stay as open balances in the control app; they are not sent to the books until paid.

## Later options

- A deposit or card on file can be added; the data model leaves room for it.
- PayPal Checkout could automate PayPal and Venmo; its Venmo button works for US merchants and customers.
- Bitcoin automation is Phase 7, with BTCPay Server on the home server and the Lightning decision made then.

## Account checks still open

The owner is to confirm the Stripe account is in the business's name and run a small Tap to Pay test, and to confirm that the Venmo and Cash App accounts are business profiles, because both restrict business use of personal accounts.
