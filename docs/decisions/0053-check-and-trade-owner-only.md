---
id: 53
title: "Check and trade are owner-only payment methods; helper pay follows the pay type"
summary: "Checks and trades are owner-only, never offered on the website; a check posts to Checking and a trade is entered by hand. Helper pay posts by pay type: family helpers to Professional Services."
date: 2026-10-14
area: payments
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/payments.md, docs/reference/bookkeeping-gnucash.md, data/gnucash-accounts.yaml, data/business.yaml]
---

# 0053: Check and trade are owner-only payment methods; helper pay follows the pay type

**Status:** accepted · **Date:** 2026-10-14 · **Area:** payments

## Context

The Baserow job history includes jobs paid by check and jobs paid in goods instead of money. Neither was in the list of payment methods. Both happen rarely and only by arrangement with the owner, and neither can be paid through the website.

The history also includes helpers paid a flat amount per job. Today every helper is a family member, paid as professional services on the advice of the owner's accountant; that is not a rule for every helper. An employee hired later would be paid normal wages per job.

## Decision

- **Check** and **trade** are payment methods the owner records in the control app. The owner accepts them case by case. They are never offered as a preferred payment method on the website.
- **A check** posts to Assets:Current Assets:Checking Account in the GnuCash export, as a direct deposit. The check number is kept as the payment's reference.
- **A trade** records what was received and its value in dollars. That value is the payment amount. A trade is left out of the GnuCash export and listed for manual entry, the same way bitcoin is until Phase 7.
- **Every helper has a pay type**, family helper or employee, and the GnuCash account for their pay comes from that pay type, not from one fixed account. Both types are paid a flat amount per job, which the owner can override for one job.
  - **Family helper**, the only type in use: pay posts to Expenses:Professional Services.
  - **Employee** is planned. It has no account yet; wages and payroll are a later decision, made before the first employee is hired.
- Each payout keeps the pay type it was made under, so past pay keeps its account if a helper's type changes.
- Helpers' names, ages, pay totals and any annual limit stay out of the repository.

## Alternatives considered

- **Record checks as cash.** Checks go to the bank, not to Petty Cash, so the export would post them to the wrong account.
- **Record a trade as a no-charge job.** The job was paid for in goods with a value, so marking it free would understate sales and sales tax.
- **One fixed account for all helper pay.** Would post a future employee's wages as professional services, against the accountant's advice, which covers family members only.

## Consequences

The payment methods in code mark check and trade as owner-only, and the website's list of methods leaves them out. A trade needs the owner's judgment in GnuCash, such as which asset or expense account the goods belong to, so it stays manual. Hiring an employee needs its own decision first, covering the wages account and payroll.

On 2026-10-17 the owner confirmed that family helper pay posts to Expenses:Professional Services. How family helpers are paid will be revisited when their help becomes regular.
