---
title: Vehicle classification
summary: How a customer's year, make and model is turned into one of the six vehicle classes and a size variant using free EPA and NHTSA data, override rules and an owner review queue.
audience: [owner, developer]
visibility: internal
status: planned
updated: 2026-10-13
tags: [vehicles, classification, phase-2]
related: [data/vehicle-classes.yaml, docs/reference/pricing.md, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md, docs/decisions/0016-size-from-vehicle-data.md]
---

# Vehicle classification

This is the Phase 2 design. Until Phase 2 is built, the owner sets the class by hand.

The customer will pick year, make and model, and the system will assign one of the six vehicle classes without asking. The classes are listed in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml).

## Data sources

| Source | What it gives | Limits |
| --- | --- | --- |
| EPA FuelEconomy.gov | Year, make and model menus from 1984 to the current model year, an EPA size class per vehicle, and the whole table as a download | Leaves out heavy-duty trucks above its weight limits and anything before 1984 |
| NHTSA vPIC | Makes and models by year for every vehicle type, free with no key | No size class; lists trailers, motorcycles and obscure makes that must be filtered out |

## How a vehicle will get its class

1. The EPA size class sets a first guess: car classes map to Coupes & Sedans, small SUVs and wagons to Crossovers & Wagons, small pickups to Light Pickups & Offroad, standard SUVs to Midsize SUVs, minivans and vans to Fullsize SUVs & Minivans, and standard pickups to Fullsize Trucks.
2. Override rules fix known mismatches, such as Jeep Wrangler to Light Pickups & Offroad, and Suburban, Expedition and Sequoia to Fullsize SUVs & Minivans. The owner edits these rules in the control app.
3. NHTSA vPIC fills the gaps the EPA leaves, mainly 2500 and 3500 series trucks.
4. A monthly job re-pulls both sources. New models the rules classify cleanly go live; ambiguous ones wait in a review queue for one click from the owner.
5. A vehicle not in the list, such as a pre-1984 classic, falls back to choosing from six photo cards, one per class.

EPA size classes are coarser for older SUVs, so those lean more on the override rules. Before launch the owner reviews the mapping for every vehicle in the job history.

## How the size variant will be set without asking

Each vehicle model will store its size rule: 1, 2 or 3 rows, or "ask".

- **Cars are priced by doors.** The EPA file records two-door and four-door body styles separately, and NHTSA's VIN records carry a door count.
- **Pickups are priced by cab.** Cab style is not part of year, make and model, so the customer is asked "regular cab, or extended or crew cab?" unless the model has one cab style.
- **Crossovers and midsize SUVs need a third-row flag.** No free source lists optional third rows cleanly: the EPA data has no seating field, and NHTSA's seat-row fields are per VIN and often blank. The flags will be seeded from NHTSA where it has data and from a prepared list for the rest; the owner checks the crossovers, midsize SUVs and pickups, and anything unknown is set to "ask".
- **The list improves itself.** When the owner corrects a vehicle's size on a job, the model's record is updated.

The door and seat-row data claims come from general knowledge of the datasets and are measured in Phase 2.

## Guarding against a wrong class

The customer sees the class with a "not right?" link, the owner sees the vehicle on every booking, and each correction becomes a rule.
