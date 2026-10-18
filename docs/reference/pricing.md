---
title: Pricing rules
summary: How every price is built from the price matrix, what size variants mean for each vehicle class, how condition and crew size change price and time, and why the quoted price is the price of record.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-17
tags: [pricing, pricebook, crew, quote]
related: [docs/decisions/0065-condition-lengthens-service-time.md, docs/decisions/0058-service-times-exclude-setup-and-breakdown.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0055-percentage-promotions-round-to-the-cent.md, data/booking-rules.yaml, data/price-matrix.csv, data/pricing-rules.yaml, data/services.yaml, data/vehicle-classes.yaml, docs/reference/pricebook-changes.md, docs/reference/sales-tax.md]
---

# Pricing rules

These rules are settled business policy. Since Phase 1 Step 3 the pricebook is in the database, loaded once by the `load_pricebook` command, and one module, the pricing engine (`app/pricebook/pricing.py`), applies these rules; the booking flow uses it from Phase 3. The numbers live in [data/price-matrix.csv](../../data/price-matrix.csv) and [data/pricing-rules.yaml](../../data/pricing-rules.yaml); this page explains them.

## The price matrix is the only price source

The owner's price matrix holds 90 prices across 10 services, each with its one-person service time. It supersedes every price on the old website; for example, Headlight Restoration is $95, not the $80 the old site showed. No price is ever hard-coded, and the final price is always calculated on the server.

A price is looked up by three things together: service, vehicle class and size variant. A combination missing from the matrix does not exist, and the pricing engine refuses to price it. A service that ignores the size variant, such as Exterior Only, has one price per vehicle class, used whatever the size variant.

## How a price is built

1. **Base price,** looked up by service, vehicle class and size variant.
2. **Condition adjustment** of 0%, 10% or 20% of the base price, for Full Detail, Interior Only and Exterior Only only. Rounded to the whole dollar. The same percentage lengthens the main service's service time ([decision 0065](../decisions/0065-condition-lengthens-service-time.md)).
3. **Add-ons,** then **promotions.** A percentage promotion is rounded to the nearest cent, an exact half cent up ([decision 0055](../decisions/0055-percentage-promotions-round-to-the-cent.md)).
4. **Sales tax** at the rate for the service address, added on top. See [sales-tax.md](sales-tax.md). Until Phase 3 adds the rate lookup, quotes carry a tax rate of zero.
5. **On-site adjustment,** entered by the owner at the job, always with a reason, shown on the invoice.

Worked example: a 2019 Toyota RAV4 (Crossovers & Wagons, two rows) booked for a Full Detail at the second condition level, with Seat Extraction. Base $250 and 5 hours, condition +10% = $25 and 0.5 hours, Seat Extraction $80 and 1.5 hours. Total $355 before tax. The service time is 5 + 0.5 + 1.5 = 7 one-person hours, and the time on site, with 30 minutes of setup and 30 of breakdown, is 8 hours, so the job is flagged as a full day.

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

## How promotions apply to a job

A promotion takes its discount off the lines for the services it applies to: the main service with its condition adjustment, and any add-ons. A promotion with no services listed applies to the whole job. A percentage is rounded to the nearest cent, an exact half cent up ([decision 0055](../decisions/0055-percentage-promotions-round-to-the-cent.md)). A dollar amount or a voucher never takes off more than those lines come to. A promotion that is inactive, outside its dates or for none of the job's services is refused.

How two promotions on one job combine has not been set by the owner. Until it is, the pricing engine applies them in the order given, each on what is left after the ones before, so the total never goes below zero.

## Condition adjustment

The customer picks one of three condition levels with plain descriptions. The first adds nothing, the second adds 10% and the third adds 20% of the base price of Full Detail, Interior Only or Exterior Only, rounded to the whole dollar. On a $280 Full Detail that is $28 or $56. The condition adjustment never applies to add-ons, paint correction, headlights or maintenance plans.

## Condition lengthens the service time

A dirtier vehicle takes longer as well as costing more ([decision 0065](../decisions/0065-condition-lengthens-service-time.md)). The condition level's percentage is added to the main service's one-person service time as well as its price, for Full Detail, Interior Only and Exterior Only only.

- **The condition line carries the extra time:** the base service hours times the percentage, unrounded. A 5-hour Full Detail at the second level adds 0.5 hours; a 5.5-hour one at the third level adds 1.1 hours.
- **Nothing else is lengthened.** Add-ons, maintenance plans, and setup and breakdown never change with condition.
- **Rounded once.** The add-on hours are added, the two-person factor is applied, and the service time is rounded to the nearest 15 minutes once, at the end. Time on site follows from that service time.
- Examples: a two-door Coupes & Sedans Full Detail at the third level is 3 + 0.6 = 3.6 hours, rounded to 3.5 hours of service and 4.5 hours on site. A two-person 2-row Midsize SUV Full Detail at the third level is (5.5 + 1.1) × 0.60 = 3.96 hours, rounded to 4 hours of service and 4.5 hours on site. The three levels follow the Armstrong booking template to start, described in the owner's own words.

## Maintenance plans are priced from Full Detail

Quarterly Maintenance is 80% and Monthly Maintenance 50% of the Full Detail price for the same vehicle class and size variant, and both take the Full Detail service hours. This is stored as a rule, not as separate prices, so changing a Full Detail price moves both. Maintenance plans are booked only by the owner, never on the website.

## Service time and time on site

The price matrix holds **service time** only: the hours spent working on the vehicle, measured for one person working alone. Setup and breakdown are not part of it ([decision 0058](../decisions/0058-service-times-exclude-setup-and-breakdown.md)). Until 2026-10-17 the matrix hours included them; every main service then dropped by 1 hour, and Headlight Restoration became 1.5 hours.

- **Time on site** is setup + service time + breakdown. Setup and breakdown are 30 minutes each for one person, divided by the number of people: 15 + 15 minutes for two. They are scheduling settings in [data/booking-rules.yaml](../../data/booking-rules.yaml), explained in [scheduling-and-calendars.md](scheduling-and-calendars.md).
- **The pricing engine returns service time.** Time on site is worked out from service time and the setup and breakdown settings. Neither changes a price.
- **The estimate card shows time on site,** because that is how long the customer's driveway is in use.

## Crew size and service time

- Matrix hours are one-person service hours.
- Two people take 60% of the one-person service time, the owner's measured figure. Crews are one or two people only.
- Service time for the crew is rounded to the nearest 15 minutes, and so is time on site. A Full Detail of 5.5 service hours at the first condition level, with two people, is 3.3 hours, rounded to 3.25 hours of service, and 3.75 hours on site.
- Monthly Maintenance defaults to a two-person crew, which puts it at 2.25 to 4.5 hours on site. Every other service defaults to one person.
- A job of 8 or more hours of one-person **time on site** (7 or more one-person service hours, condition time included) is flagged in the control app for a second person, and the customer's estimate card shows "full day" instead of hours. A higher condition level can therefore make a job a full day. Long jobs are allowed; nothing blocks them.

## The quoted price is the price of record

The website and the control app show the same price from one source, and the owner is told about any change between booking and the appointment ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)).

- **One source.** Only the server's pricing engine computes prices. The website's estimate card and the control app display its results and do no arithmetic of their own.
- **The price shown is the price booked.** The server issues a quote record holding the inputs, lines, totals, pricebook version, tax rate, service time and time on site. A quote never changes once issued. A booking refers to the quote, never to a price sent from the browser, and the quote's lines become the appointment's line snapshot exactly ([decision 0033](../decisions/0033-pricebook-versions-and-line-snapshots.md)). A quote books one appointment. The control app never re-prices a booked job. The quote record exists since Phase 1 Step 3; the website will use it in Phase 3.
- **The owner is notified of any change.** If a booked job's price changes for any reason other than a choice the owner made, such as a sales tax rate change, the owner gets a push alert and the control app shows the booked total beside the new one. The owner's own edits need a reason and are logged.
- **Sales tax** is charged at the rate on the day of service. If the rate changes after booking, the new rate applies and the owner is notified; the price before tax never changes. See [sales-tax.md](sales-tax.md).
- **Nothing extra.** There is no customer re-confirmation step, no quote-number text, no nightly price check and no end-to-end booking test; the normal test suite covers pricing.

## Room for another price basis

Every vehicle class is priced from the fixed price list today. Each vehicle class records its price basis, and the pricing engine looks up a class's base price through that basis, so a class could later be priced another way, such as per foot of length for RVs, by adding one new basis without changing the rest of the engine. Only the fixed price list is built.

## Custom lines

Misc Services is an owner-only line for a one-off job at a price the owner sets. PPF Removal and Trim Restoration exist only as past services until the owner prices them.
