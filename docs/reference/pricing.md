---
title: Pricing rules
summary: How every price is built from the price matrix, what size variants mean for each vehicle class, how condition and crew size change price and time, and the rules that keep prices consistent.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-14
tags: [pricing, pricebook, crew]
related: [docs/decisions/0055-percentage-promotions-round-to-the-cent.md, data/price-matrix.csv, data/pricing-rules.yaml, data/services.yaml, data/vehicle-classes.yaml, docs/reference/pricebook-changes.md, docs/reference/sales-tax.md]
---

# Pricing rules

These rules are settled business policy. The pricebook is loaded into the system in Phase 1 and applied by the booking flow in Phase 3. The numbers live in [data/price-matrix.csv](../../data/price-matrix.csv) and [data/pricing-rules.yaml](../../data/pricing-rules.yaml); this page explains them.

## The price matrix is the only price source

The owner's price matrix holds 90 prices across 10 services, each with a one-person job length. It supersedes every price on the old website; for example, Headlight Restoration is $95, not the $80 the old site showed. No price is ever hard-coded, and the final price is always calculated on the server.

A price is looked up by three things together: service, vehicle class and size variant. A combination missing from the matrix does not exist.

## How a price is built

1. **Base price,** looked up by service, vehicle class and size variant.
2. **Condition adjustment** of 0%, 10% or 20% of the base price, for Full Detail, Interior Only and Exterior Only only. Rounded to the whole dollar.
3. **Add-ons,** then **promotions.** A percentage promotion is rounded to the nearest cent, an exact half cent up ([decision 0055](../decisions/0055-percentage-promotions-round-to-the-cent.md)).
4. **Sales tax** at the rate for the service address, added on top. See [sales-tax.md](sales-tax.md).
5. **On-site adjustment,** entered by the owner at the job, always with a reason, shown on the invoice.

Worked example: a 2019 Toyota RAV4 (Crossovers & Wagons, two rows) booked for a Full Detail at the second condition level, with Seat Extraction. Base $250, condition +10% = $25, Seat Extraction $80. Total $355 before tax, about 7.5 one-person hours.

## What the size variant means for each vehicle class

The matrix's size column holds 1, 2 or 3. What it measures depends on the vehicle class.

| Vehicle class | What sets the size variant | Customer asked? |
| --- | --- | --- |
| Coupes & Sedans | Doors, not seats: two doors takes the 1-row price, four doors the 2-row price. Hatchbacks follow the door count; convertibles are two-door | Only when a model is sold both ways: "two doors or four doors?" |
| Crossovers & Wagons | Seat rows, from a per-model flag: always 2, always 3, or optional third row | Only for an optional third row |
| Midsize SUVs | Seat rows, from the same per-model flag | Only for an optional third row |
| Fullsize SUVs & Minivans | Always 3 | Never |
| Light Pickups & Offroad, Fullsize Trucks | Cab style: regular cab = 1, extended or crew cab = 2 | As a cab question, unless the model has only one cab style |

Exterior Only, both paint corrections and Headlight Restoration ignore the size variant. How the system sets the size variant from the vehicle is in [vehicle-classification.md](vehicle-classification.md).

## Condition adjustment

The customer picks one of three condition levels with plain descriptions. The first adds nothing, the second adds 10% and the third adds 20% of the base price of Full Detail, Interior Only or Exterior Only, rounded to the whole dollar. On a $280 Full Detail that is $28 or $56. The condition adjustment never applies to add-ons, paint correction, headlights or maintenance plans. The three levels follow the Armstrong booking template to start, described in the owner's own words.

## Maintenance plans are priced from Full Detail

Quarterly Maintenance is 80% and Monthly Maintenance 50% of the Full Detail price for the same vehicle class and size variant, and both take the Full Detail hours. This is stored as a rule, not as separate prices, so changing a Full Detail price moves both. Maintenance plans are booked only by the owner, never on the website.

## Crew size and job length

- Matrix hours are one-person hours.
- Two people take 60% of the one-person time, the owner's measured figure. Crews are one or two people only.
- Job time is rounded to the nearest 15 minutes. A 6.5-hour Full Detail becomes 4 hours with two people.
- Monthly Maintenance defaults to a two-person crew, which puts it at 2.5 to 4.5 hours. Every other service defaults to one person.
- A job totalling 8 or more one-person hours is flagged in the control app for a second person, and the customer's estimate card shows "full day" instead of hours. Long jobs are allowed; nothing blocks them.

## Custom lines

Misc Services is an owner-only line for a one-off job at a price the owner sets. PPF Removal and Trim Restoration exist only as past services until the owner prices them.
