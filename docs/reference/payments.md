---
title: Payments
summary: How each payment method is taken at the job and marked paid, and the payment rules that apply to every appointment.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [payments, stripe, billing]
related: [docs/reference/bookkeeping-gnucash.md, docs/decisions/0008-stripe-and-manual-payments.md, docs/decisions/0009-bitcoin-later-phase.md]
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

## Rules for every payment

- **Totals include sales tax,** shown as its own line on the payment link and the receipt.
- **Tips** are recorded separately and are not taxed.
- **Card details never touch the server.** Stripe handles them.
- **Gift cards and prepayments** are recorded as payments before the job, so the appointment shows as already paid.
- **Unpaid finished jobs** stay as open balances in the control app; they are not sent to the books until paid.

## Later options

- A deposit or card on file can be added; the data model leaves room for it.
- PayPal Checkout could automate PayPal and Venmo; its Venmo button works for US merchants and customers.
- Bitcoin automation is Phase 7, with BTCPay Server on the home server and the Lightning decision made then.

## Account checks still open

The owner is to confirm the Stripe account is in the business's name and run a small Tap to Pay test, and to confirm that the Venmo and Cash App accounts are business profiles, because both restrict business use of personal accounts.
