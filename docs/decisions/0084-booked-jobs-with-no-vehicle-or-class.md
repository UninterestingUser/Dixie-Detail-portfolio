---
id: 84
title: "A booked job in a retired class with no vehicle, class or size is not re-priced and is checked by hand"
summary: "When a new price book re-prices a job booked in a retired class, a job with no vehicle, or a vehicle with no class or size variant, keeps its quoted price and is listed to check by hand."
date: 2026-10-28
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: []
related: [docs/decisions/0083-applying-the-size-based-classes.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/operations/classifying-vehicles.md, docs/operations/using-the-catalog-screens.md, docs/operations/troubleshooting.md]
---

# 0084: A booked job in a retired class with no vehicle, class or size is not re-priced and is checked by hand

**Status:** accepted · **Date:** 2026-10-28 · **Area:** pricing

## Context

Decision 0083 re-prices a booked job whose class is retired in its vehicle's new class, to show the owner its price under the new book. The owner's first `apply_size_classes` dry run stopped with an error: an upcoming appointment had no vehicle. Others may have a vehicle with no class or no size variant, such as one recorded with no year that the catalog cannot class. Publishing a draft from the control app's price book page uses the same code and would stop the same way.

## Decision

1. **Such a job is not re-priced.** A job booked in a retired class with no vehicle, or whose vehicle has no live class, or no size variant of a class that has them, keeps its quoted price, the price of record (decision 0059).
2. **It is listed to check by hand:** "no vehicle or class: check by hand", with the appointment's date and id, on the version's booked-job review and the control app's publish screen, and in its own section of the `apply_size_classes` report. Command output never names the customer. The owner can keep it or give a custom amount, or give the vehicle its class and size first.
3. **A failure nobody foresaw stops cleanly.** If `apply_size_classes` fails partway for any other reason, its error says which step it was on and which appointment or vehicle it was working on, and the transaction changes nothing. Publishing from the control app shows the same message and publishes nothing.

A job booked in a class that is still offered is re-priced from its own lines, as before; its vehicle does not matter.

## Alternatives considered

- **Re-price it in the class proposed from its old one.** That is a guess about a vehicle nobody has classed; the differences screen is where that guess is confirmed.
- **Leave it out of the list.** The owner would not see that the job still names a retired class.

## Consequences

The dry run and the switch finish with such jobs present. The owner settles each by hand after the switch, as with vehicles left in a retired class.
