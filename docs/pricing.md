# Pricing

The price matrix in [../data/price-matrix.csv](../data/price-matrix.csv) is the only source of prices. It supersedes everything on the old website.

## How a price is built

1. **Base price,** looked up by service, vehicle class and size variant.
2. **Condition adjustment:** 0%, 10% or 20% of the base price, for Full Detail, Interior Only and Exterior Only only. Rounded to the whole dollar. Add-ons are not affected.
3. **Add-ons,** then **promotions.**
4. **Sales tax** at the rate for the service address, added on top.
5. **On-site adjustment,** entered by the owner at the job with a reason, shown on the invoice.

Example: a Midsize SUV with two rows, Full Detail, third condition level. The base is $280, plus 20% ($56), giving $336 before add-ons and tax.

## Services

| Service | Price varies by | Price (USD) | One-person hours | Booked by |
| --- | --- | --- | --- | --- |
| Full Detail | Class and size | 200 to 330 | 4 to 7.5 | Customer or owner |
| Interior Only | Class and size | 110 to 200 | 2 to 4 | Customer or owner |
| Exterior Only | Class | 110 to 170 | 2 to 3.5 | Customer or owner |
| 1-Step Paint Correction | Class | 300 to 450 | 6 to 7.5 | Customer or owner |
| 2-Step Paint Correction | Class | 450 to 750 | 8 to 10 | Customer or owner |
| Headlight Restoration | One price | 95 | 2 | Customer or owner |
| Carpet Extraction (add-on) | Seat rows | 50, 70 or 90 | 1 to 2 | Customer or owner |
| Seat Extraction (add-on) | Seat rows | 60, 80 or 100 | 1 to 2 | Customer or owner |
| Quarterly Maintenance | Class and size | 160 to 264 | 4 to 7.5 | Owner only |
| Monthly Maintenance | Class and size | 100 to 165 | 4 to 7.5 (2.5 to 4.5 with two people) | Owner only |

## Rules

- **Maintenance follows Full Detail.** Quarterly is 80% and Monthly is 50% of the Full Detail price for the same class and size, with the Full Detail hours. Stored as a rule, not as separate prices.
- **Condition levels** follow the Armstrong template to start: the first adds nothing, the second 10%, the third 20%. Descriptions are written in the owner's own wording.
- **The matrix is complete.** A class and size combination missing from the CSV does not exist.

## Size variants

The CSV's `size_variant` column holds 1, 2 or 3. What it means depends on the class.

| Class | What sets the size | Customer asked? |
| --- | --- | --- |
| Coupes & Sedans | Doors: two doors = 1, four doors = 2. Hatchbacks follow the door count; convertibles are two-door. | Only when a model is sold both ways: "two doors or four doors?" |
| Crossovers & Wagons | Seat rows, from a per-model flag: always 2, always 3, or optional third row | Only for an optional third row |
| Midsize SUVs | Seat rows, from the same per-model flag | Only for an optional third row |
| Fullsize SUVs & Minivans | Always 3 | Never |
| Light Pickups & Offroad, Fullsize Trucks | Cab: regular = 1, extended or crew = 2 | As a cab question, unless the model has one cab style |

Per-model flags are seeded from EPA and NHTSA data plus a prepared list, reviewed by the owner, and updated whenever the owner corrects a vehicle on a job.

## Crew and job time

- Matrix hours are one-person hours.
- Two people take 60% of the one-person time. Crews are one or two people only.
- Job time is rounded to the nearest 15 minutes.
- Monthly Maintenance defaults to two people; every other service to one.
- A job totalling 8 or more one-person hours is flagged in the control app for a second person, and the customer's estimate card shows "full day" instead of hours.

## Sales tax

- Added on top of the final price as its own line on the estimate, invoice and receipt.
- The rate is the one for the customer's service address. The address is geocoded with the Census Bureau geocoder, then matched against the Tennessee Department of Revenue's boundary data.
- If an address will not match, the job takes its county's rate and is flagged for the owner.
- Stored rates are checked against the state's data on a schedule, and any change waits for owner approval.
- Every invoice stores the taxable amount, state tax, local tax and jurisdiction. Tax posts to Sales Tax Payable, never to income.
- The sourcing rule (service address or business location) is a single setting, in case the accountant advises the other.
