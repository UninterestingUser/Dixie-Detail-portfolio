---
id: 66
title: "Imported payments are held by an \"already in GnuCash\" export batch; a split keeps both methods"
summary: "Payments and helper payouts imported from Baserow belong to one export batch, so the GnuCash export never sends them again; a payment split between two methods records both."
date: 2026-10-17
area: migration
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/data-migration.md, docs/operations/importing-baserow.md, docs/reference/bookkeeping-gnucash.md, docs/decisions/0035-gnucash-account-mapping.md, docs/decisions/0036-baserow-import.md, docs/decisions/0051-baserow-ids-kept-on-import.md]
---

# 0066: Imported payments are held by an "already in GnuCash" export batch; a split keeps both methods

**Status:** accepted · **Date:** 2026-10-17 · **Area:** migration

## Context

Every payment and helper payout in Baserow's Bookkeeping table is already in the owner's GnuCash books. The Phase 6 export sends each payment, refund and payout that no export batch holds yet (decision 0035), so imported ones would be sent twice. Some Bookkeeping rows list two payment methods, such as "Cash,Venmo", without saying how much went each way, and a payment had one method. A re-run of the import must update payments rather than add them again (decision 0051), and payments have no Baserow id of their own.

## Decision

- **Already in the books.** The import creates one export batch, "Already in GnuCash: Baserow import", covering the dates of the imported payments, and every imported payment and helper payout belongs to it. The export never sends them.
- **Split payments.** A Bookkeeping row with two methods is one payment, with its first method and the second as its split method. The split amounts were never recorded and are not invented.
- **Import keys.** Imported payments, helper payouts and addresses carry an import key naming where they came from, such as "bookkeeping:123", so a re-run finds and updates them.

## Alternatives considered

- **A flag on each payment instead of a batch.** The export would need a second rule; with a batch, "not yet in a batch" stays the one rule.
- **Two payments, splitting the amount evenly or by a guess.** Would put invented amounts in the books.

## Consequences

The Phase 6 export needs no special case for imported records. Reports by payment method show split payments under both methods, without amounts per method.
