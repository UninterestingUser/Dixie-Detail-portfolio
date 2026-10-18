---
title: Moving existing records
summary: How customers, vehicles, appointments, payments and staff are imported from Baserow, with Setmore filling gaps, how each export format is converted, and how re-runs update.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-18
tags: [migration, import, baserow, setmore, phase-1]
related: [docs/operations/importing-baserow.md, docs/decisions/0036-baserow-import.md, docs/decisions/0051-baserow-ids-kept-on-import.md, docs/decisions/0066-imported-payments-already-in-the-books.md, docs/reference/returning-customers.md, docs/architecture/data-model.md]
---

# Moving existing records

Baserow is the source for the import, built in Phase 1 and run before launch. The Setmore contact list only fills gaps. After launch both are retired. These rules were settled with the owner on 2026-10-11 and are applied by the `import_baserow` command; how to run it is in [../operations/importing-baserow.md](../operations/importing-baserow.md).

## Where the source files live

The source files are the owner's exports: the Baserow Customers, Vehicles, Appointments and Bookkeeping tables, and the Setmore contact list. Setmore cannot export appointments. The files hold personal data, so they stay outside the repository and outside these docs. So does `import-corrections.yaml`, the list of per-record corrections agreed with the owner (spellings, merged duplicates, address and ZIP fixes, second contacts, no-charge and prepaid jobs); the import reads it from the same private folder as the exports. Its own `meta` and `rules` sections describe it.

## What happens to each kind of record

| Records (counts as of 2026-10-11) | What happens |
| --- | --- |
| 104 customers | Imported with the agreed corrections. Customers without a phone number are kept |
| Second contacts | Four second contacts are added to existing customers, as listed in the corrections file. The Setmore-only contacts it lists as not imported are skipped |
| 128 vehicles | Imported as they are. Missing year, make or model is flagged to fill in at the next visit. Two motorcycles come over as past records with no vehicle class |
| 174 completed jobs (from 2025-05-22) | Kept as history at the price actually charged, with promotions and notes |
| 10 booked jobs (through 2026-12-11) | Carried over as live appointments. One prepaid job imports as already paid |
| Payments | From the Bookkeeping table, already in GnuCash, so never exported again |
| Staff | Assignments for every name in the Staff column, with helper pay where Baserow records it |

## How rows are matched

- **Each imported record keeps its Baserow id** (decision 0051): customers, vehicles and appointments by their row id; payments by their Bookkeeping row; addresses and helper payouts by the row they came from. A re-run with fresh exports updates them instead of duplicating them.
- **Links between tables are display strings,** such as "First Last - 4235551234". A customer link matches the customer with that exact display, or else the same name and the last 10 digits of the phone, or else a name only one customer has.
- **A vehicle link** matches a vehicle of that name belonging to the appointment's customer. Where the customer has two of the same name, the vehicle's own Appointments column, then the vehicle class and seat rows, tell them apart; a job still undecided keeps no vehicle and is reported.
- **A vehicle named in the corrections file wins.** An `appointment_fixes` entry with `set: {vehicle_baserow_id: N}` links that appointment to the Baserow vehicle with id N, for a customer with two vehicles of the same name. The report lists it under "Corrections applied". It is used only when vehicle N was imported and belongs to the appointment's customer; otherwise it is listed under "Could not place" and the usual matching applies.
- **An appointment's Bookkeeping value** equals exactly one Bookkeeping row's Name; that row holds the job's payment.
- **Setmore contacts** match a Baserow customer by phone number, or as named in the corrections file.

## Conversions

- **Times.** Baserow writes appointment and payment times in UTC (`MM/DD/YYYY hh:mm AM`); they are stored in UTC and show in Eastern. This was verified against a known job: a 3:30 PM UTC entry is an 11:30 AM appointment.
- **Phone numbers.** The last 10 digits are kept: Baserow stores some numbers with a leading 1, and Setmore uses +1.
- **Services.** The Service Name cell is "Class - Service (N Rows)" with add-ons after commas. Interior Detail becomes Interior Only, Exterior Detail becomes Exterior Only, and "Paint Correction 1-Step" and "2-Step" become 1-Step and 2-Step Paint Correction. Misc Services becomes a custom line at the price charged. PPF Removal and Trim Restoration stay as past services, off the price list until priced.
- **Seat rows.** Seating such as "2 Rows" sets the vehicle's size variant where its vehicle class has that size.
- **Prices.** A job's lines add up to the price actually charged: the services at Baserow's list price (all of it on the first service line, since Baserow does not split it by service), any promotion as its own line, then a price adjustment line, with a reason, for any override, so the total is the Final Price. A promotion a past job used is created inactive if it does not exist yet, for the owner to check.
- **No-charge jobs.** A completed job with a Final Price of $0 is a no-charge job with a reason, not an unpaid one.
- **Motorcycles** and jobs with no service recorded import as a custom line at the price charged, because they are not on the price list.
- **Hours.** Hours (`h:mm`) is the job's whole time on site. Setup and breakdown are split from it by the crew size, using the launch values, and the rest is service time. Jobs with no Hours keep no times.
- **Payments.** Payments, tips and payment methods come from Bookkeeping. Customer Paid includes the tip, so the payment is Customer Paid less the tip. A negative tip is written `'-$5`. Cash.App is Cash App direct to the owner's $cashtag.
- **Split payments.** A payment listing two methods, such as "Cash,Venmo", is one payment recorded as split between the two; the split amounts were never recorded (decision 0066).
- **Already in the books.** Every imported payment and helper payout belongs to the export batch "Already in GnuCash: Baserow import", so the Phase 6 GnuCash export never sends it (decision 0066).
- **Staff.** The Staff column can list two names; the crew size is the number listed. A name is matched to a staff member, or created: the owner as named on the first run, everyone else as a family helper. Wage Override in Bookkeeping is the helper's pay for that job, and "Employees Paid" 1 adds a helper payout. Baserow does not record how a helper was paid, so the payout is entered as cash with a note.
- **Booked jobs and the pricebook.** Booked jobs keep the prices they were quoted, as line snapshots. See [pricebook-changes.md](pricebook-changes.md).

## Checking the import

Every run, dry or applied, prints a report: counts of each kind of record, every correction applied, warnings, every row it could not place and why, the open questions in the corrections file, and the corrections file's expected results to compare. Phase 1's done test includes searching the imported history. The owner spot-checks that every booked job, its time and its price came across correctly before Setmore is switched off.
