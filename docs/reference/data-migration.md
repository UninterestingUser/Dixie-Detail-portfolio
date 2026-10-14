---
title: Moving existing records
summary: How customers, vehicles and appointments are imported once from Baserow, with Setmore filling gaps, before both are retired.
audience: [owner, developer]
visibility: internal
status: planned
updated: 2026-10-13
tags: [migration, import, baserow, setmore, phase-1]
related: [docs/decisions/0036-baserow-import.md, docs/reference/returning-customers.md, docs/architecture/data-model.md]
---

# Moving existing records

Baserow is the source for the one-time import, built in Phase 1 and run before launch. The Setmore contact list only fills gaps. After launch both are retired. These rules were settled with the owner on 2026-10-11.

## Where the source files live

The source files are the owner's exports: Baserow Customers, Vehicles and Appointments, and the Setmore contact list. Setmore cannot export appointments. The files hold personal data, so they stay outside the repository and outside these docs. So does the list of per-record corrections agreed with the owner (spellings, merged duplicates, address and ZIP fixes); the import reads it from the same private folder as the exports.

## What happens to each kind of record

| Records (counts as of 2026-10-11) | What happens |
| --- | --- |
| 104 customers | Imported with the agreed corrections. Customers without a phone number are kept |
| Second contacts | Four second contacts are added to existing customers: two Setmore-only contacts and two found in Baserow. The other 8 Setmore-only contacts are not imported |
| 128 vehicles | Imported as they are. Missing year, make or model is flagged to fill in at the next visit. Two motorcycles come over as past records with no vehicle class |
| 174 completed jobs (from 2025-05-22) | Kept as history at the price actually charged, with promotions and notes |
| 10 booked jobs (through 2026-12-11) | Carried over as live appointments. One prepaid by gift card imports as already paid |

## Conversions

- **Times.** Baserow stores appointment times in UTC; they are converted to Eastern. This was verified against a known job: a 3:30 PM UTC entry is an 11:30 AM appointment.
- **Services.** Interior Detail becomes Interior Only, and Exterior Detail becomes Exterior Only. Misc Services becomes a custom line the owner can add to any job at a custom price. PPF Removal and Trim Restoration stay as past services, off the price list until priced.
- **Booked jobs and the pricebook.** Booked jobs keep the prices they were quoted, as line snapshots. See [pricebook-changes.md](pricebook-changes.md).

## Checking the import

Phase 1's done test includes searching the imported history. The owner spot-checks that every booked job, its time and its price came across correctly before Setmore is switched off.
