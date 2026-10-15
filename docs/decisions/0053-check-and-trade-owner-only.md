---
id: 53
title: "Check and trade are owner-only payment methods"
summary: "Checks and trades (goods instead of money) are accepted by the owner case by case and never offered on the website; a check posts to Checking and a trade is entered by hand."
date: 2026-10-14
area: payments
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/payments.md, docs/reference/bookkeeping-gnucash.md, data/gnucash-accounts.yaml, data/business.yaml]
---

# 0053: Check and trade are owner-only payment methods

**Status:** accepted · **Date:** 2026-10-14 · **Area:** payments

## Context

The Baserow job history includes jobs paid by check and jobs paid in goods instead of money. Neither was in the list of payment methods. Both happen rarely and only by arrangement with the owner, and neither can be paid through the website.

## Decision

- **Check** and **trade** are payment methods the owner records in the control app. The owner accepts them case by case. They are never offered as a preferred payment method on the website.
- **A check** posts to Assets:Current Assets:Checking Account in the GnuCash export, as a direct deposit. The check number is kept as the payment's reference.
- **A trade** records what was received and its value in dollars. That value is the payment amount. A trade is left out of the GnuCash export and listed for manual entry, the same way bitcoin is until Phase 7.

## Alternatives considered

- **Record checks as cash.** Checks go to the bank, not to Petty Cash, so the export would post them to the wrong account.
- **Record a trade as a no-charge job.** The job was paid for in goods with a value, so marking it free would understate sales and sales tax.

## Consequences

The payment methods in code mark check and trade as owner-only, and the website's list of methods leaves them out. A trade needs the owner's judgement in GnuCash, such as which asset or expense account the goods belong to, so it stays manual.
