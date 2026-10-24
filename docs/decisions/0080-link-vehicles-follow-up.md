---
id: 80
title: "Vehicles with no year link by make and model, customer aliases can hold for some years, and motorcycle-only makes give the Motorcycles class"
summary: "Fixes from the first link_vehicles dry run: year-less vehicles link by name and keep their class; year-limited aliases; motorcycles by make; a name check for every unlinked vehicle."
date: 2026-10-24
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-24
supersedes: []
superseded_by: []
related: [docs/decisions/0077-linking-vehicles-to-the-catalog.md, docs/decisions/0078-imported-motorcycle-jobs-get-their-class.md, docs/decisions/0079-approval-list.md, docs/operations/linking-vehicles.md, docs/reference/vehicle-classification.md, data/vehicle-names.yaml, data/vehicle-data-import.yaml]
---

# 0080: Vehicles with no year link by make and model, customer aliases can hold for some years, and motorcycle-only makes give the Motorcycles class

**Status:** accepted · **Date:** 2026-10-24 · **Area:** vehicles

## Context

The owner's first `link_vehicles --dry-run` left many vehicles unlinked only because Baserow had no year for them. A vehicle with no year was reported as "no year recorded" without its name ever being tried, so a misspelling behind a missing year could not be seen, and its model was missing from the approval list. Customers also name some vehicles in ways the catalog files elsewhere: a 2015 "Dodge Ram" is the Ram 1500, because Ram became its own make for 2011, and "Chevrolet 2500" is the Silverado HD. Two Harley-Davidson jobs had no model at all, so they could not be linked to a motorcycle model and missed the Step 4 motorcycle change (decision 0078).

## Decision

1. **A vehicle with no year links by make and model** when the name fits exactly one catalog model. It keeps the class and size variant it was imported with, its year stays in `missing_details` for the next visit, and the report lists it as "linked, year unknown". It is not compared on the differences screen, because the class depends on the year. A name that fits several catalog models, such as two owner records for different years, is left unlinked.
2. **The approval list's job history goes by make and model:** every catalog model with the name of a vehicle in the job history, linked or not, with or without a year, and every record of a linked model's name. Each model shows all its year ranges.
3. **Customer aliases** in `data/vehicle-names.yaml` (`customer_aliases`) name a vehicle the catalog files under another name or make, and may hold only from or to a model year. Outside those years the name means what it says; with no year recorded, a year-limited alias leaves the vehicle for the owner. They are read by `link_vehicles` only, so the vehicle data import never merges catalog models because of them. A model name that starts with its make, such as "Ram 1500" for a Ram, is also tried without it.
4. **Motorcycle-only makes.** `data/vehicle-data-import.yaml` marks the motorcycle makes that sell no cars, trucks or vans in the US (`motorcycles_only`): Harley-Davidson, Indian, Ducati, Yamaha, Kawasaki, Triumph, KTM, Aprilia, Moto Guzzi, Royal Enfield, Husqvarna, Victory and Zero, but not Honda, Suzuki or BMW. A vehicle of such a make, or one linked to a motorcycle model with no year, gets the Motorcycles class when it has none, even with no model, and its imported jobs get the change in decision 0078.
5. **A name check** in the report says, for every unlinked vehicle with a make and model, whether the name would match once a year is known, and what it matches.

## Alternatives considered

- **Leave year-less vehicles unlinked until a visit fills the year.** Their models would stay off the approval list, and their spellings unchecked.
- **Put the year-limited names in the ordinary alias list.** The import uses that list to merge catalog models, and has no year to go by.
- **Give the Motorcycles class to every motorcycle make.** Honda, Suzuki and BMW also sell cars.

## Consequences

More of the job history links on the first real run, and the report shows each remaining spelling problem. A year-less vehicle's class is checked by the owner when its year is filled in; then the next run compares it with the catalog. A make that starts selling cars needs its `motorcycles_only` flag removed.
