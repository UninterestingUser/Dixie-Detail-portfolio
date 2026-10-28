---
id: 83
title: "The size-based classes are applied in one step with the new price book, with vans before pickups, a pickup line at 760 cu ft and smoothing"
summary: "apply_size_classes publishes the new price book and switches every model year and vehicle to the size-based classes at once; vans before pickups, a 760 cu ft pickup line, smoothing."
date: 2026-10-28
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: [docs/decisions/0072-motorcycles-class.md, docs/decisions/0079-approval-list.md]
superseded_by: []
related: [docs/decisions/0082-size-based-vehicle-classes.md, data/size-classes.yaml, data/vehicle-classes.yaml, data/price-matrix.csv, data/approval-spot-checks.yaml, docs/reference/vehicle-classification.md, docs/reference/pricing.md, docs/operations/classifying-vehicles.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0081-monthly-vehicle-data-refresh.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md]
---

# 0083: The size-based classes are applied in one step with the new price book, with vans before pickups, a pickup line at 760 cu ft and smoothing

**Status:** accepted · **Date:** 2026-10-28 · **Area:** vehicles

## Context

Decision 0082 chose the size-based classes and left applying and pricing them to a later step, after a dry run. The owner read the dry run and asked on 2026-10-28 for the switch, with a new price book in `data/price-matrix.csv` and these changes to the rules. The dry run showed vans of a heavy-duty series (a ProMaster 2500, an Express 3500) caught by the heavy-pickup rule; pickups split only by the EPA's label, which moved the Tacoma and others between classes by year; and models flipping class for a year or two where their box volume sat near a line. Classes and prices change together, so they must switch in one step: a size-based class with no price, or a price for a class not offered yet, would break booking.

## Decision

1. **Vans come before pickups.** The van models listed in `data/size-classes.yaml` (ProMaster, Transit, Sprinter, Express, Savana, E-Series, NV and similar) are left out of every pickup rule, so no van is ever a pickup. A van is classed by size like any other vehicle: large vans land in Full-size Vans, small ones such as the Transit Connect, ProMaster City, NV200 and Metris wherever their box volume puts them.
2. **A pickup size line at 760 cubic feet.** A pickup with a box volume is a Light Pickup under 760 and a Full-size Truck at 760 and up. A pickup with no box volume in any year falls back to its EPA label: small pickups to Light Pickups, standard pickups and heavy-duty trucks to Full-size Trucks.
3. **Fullsize Trucks is renamed Full-size Trucks,** and Light Pickups & Offroad Light Pickups, as decision 0082 said; each is the same record under its new name.
4. **Smoothing.** A run of up to six model years between two runs of the same class takes that class. Model overrides, review queue decisions and next year's models carried from the nearest year are never smoothed. The reports list every smoothed run.
5. **Three model overrides:** the Audi Q4 e-tron 2022 to 2026 is Medium, the Porsche Cayenne 2026 Large, and the BMW iX 2026 Medium.
6. **A customer's vehicle with no year** takes the class of its model's newest generation (its newest model years whose length, width and height each stay within an inch), flagged so the year is confirmed at the next visit.
7. **The new price book** prices Small, Medium, Large, Full-size, Light Pickups, Full-size Trucks and Motorcycles. Full-size Vans is booked by quote and has no prices. The Motorcycle Detail is 2 hours of service, not 1 as decision 0072 set.
8. **A price book check** refuses a price book where Monthly Maintenance is not 50% and Quarterly Maintenance 80% of Full Detail for the same class and size, where a maintenance plan's hours are not Full Detail's, or where a class and row count the rules can give has no Full Detail price (or, for Motorcycles, no Motorcycle Detail price); a class booked by quote needs none. `load_pricebook` runs it on the file, `apply_size_classes` on the draft with every class and size the classified catalog gives, and the tests on the file.
9. **One step.** `load_pricebook` loads the new price book as a draft, and the new classes wait as pending, not offered. `apply_size_classes --effective YYYY-MM-DD`, run on the effective date, then does everything in one transaction: it publishes the draft, renames and offers classes, retires the body-type classes, archives the old rules, model overrides, review queue decisions and approvals, creates the size-based rules and overrides, classifies every model year, sets each customer's vehicle's class and runs the price book check, which rolls everything back if it fails. `--dry-run` does all of it, prints the same report and rolls back. The draft cannot be published any other way.
10. **Retired classes are kept for history.** Past appointments and their quote lines keep the class they had; a retired class is hidden from booking, quoting and the catalog, and never priced again. Archived rules, overrides, decisions and approvals stay in history but are no longer used.
11. **Customers' vehicles** take the class the size-based classes give, with the newest-generation rule. A vehicle left in a retired class, because it is not linked or its model year has no class, goes on the differences screen with a class proposed from its old one, for the owner.
12. **Booked jobs keep their quoted price,** the price of record (decision 0059). The switch logs no choice for them; the version's booked-job review lists each with its quoted price and its price in its vehicle's new class, and the owner chooses. Nothing changes without the owner.
13. **Photo cards** for every class show the class name, a few example models kept in `data/vehicle-classes.yaml` and a photo, with a placeholder until the owner adds one. Full-size Vans' card asks for a photo for a quote.
14. **The approval list starts over.** It lists the job-history models, a new spot-check list in `data/approval-spot-checks.yaml` (some entries for certain model years), every model with model years from 2015 on within 5 cubic feet of a size line or the pickup line, and every model approved since. It no longer lists every model whose years are in different classes, which decision 0079 added.
15. **The monthly refresh** classifies new model years with the size-based rules, and its log holds only the model years newly sent to the review queue and its one-line summary.

This record replaces the Motorcycle Detail's 1 hour of service in [decision 0072](0072-motorcycles-class.md), and the mixed-class models on the approval list in [decision 0079](0079-approval-list.md). The rest of both stands.

## Alternatives considered

- **Switch the classes now and publish the prices on a later effective date.** Between the two, a size-based class would have no price in effect, so the switch runs on the effective date instead.
- **Publish the draft from the control app and switch the classes separately.** Two steps can be run apart or in the wrong order; one transaction cannot.
- **Reprice booked jobs in their new class automatically.** The quoted price is the price of record; the owner decides each job.
- **Carry the old approvals forward where the class name survived.** The "how" of every model year changed, so each approval would be about a different answer.
- **List vans as their own rule ahead of the pickups, class by class.** A van rule for each size class repeats every line; leaving vans out of the pickup rules keeps the lines in one place.

## Consequences

The owner runs `load_pricebook`, a dry run of `apply_size_classes`, and then `apply_size_classes` on the effective date ([../operations/classifying-vehicles.md](../operations/classifying-vehicles.md#applying-the-size-based-classes)). Until then the body-type classes and rules stay live and `classify_vehicles` leaves them as they are. If the catalog gives a class and size the price book leaves out, such as a two-row vehicle in Full-size, the check refuses the switch and names the model years, so the owner adds the price or a size first. After the switch the owner settles the vehicles left in a retired class on the differences screen, the booked jobs on the booked-job review, and approves the new approval list.
