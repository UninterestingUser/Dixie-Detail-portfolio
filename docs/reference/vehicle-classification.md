---
title: Vehicle classification
summary: How a customer's year, make and model will be turned into a vehicle class and size variant, using free EPA and NHTSA data, owner-editable classification rules, overrides and a review queue.
audience: [owner, developer]
visibility: internal
status: planned
updated: 2026-10-17
tags: [vehicles, classification, phase-2]
related: [docs/decisions/0060-vehicle-classification-rules-are-data.md, data/vehicle-classes.yaml, data/integrations.yaml, docs/reference/pricing.md, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md, docs/decisions/0016-size-from-vehicle-data.md]
---

# Vehicle classification

This is the Phase 2 design. Until Phase 2 is built, the owner sets the class by hand.

The customer will pick year, make and model, and the system will assign one of the six vehicle classes without asking. Booking stays year, make and model: VINs are not used for pricing, because the owner sees a VIN only on site. The classes are listed in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml). The six-class structure stays; classes and size variants are already records the owner can change (Phase 1).

## Data sources

| Source | What it gives | Limits |
| --- | --- | --- |
| EPA FuelEconomy.gov | Year, make and model menus from 1984 to the current model year, an EPA size class per vehicle, and the whole table as a download | Leaves out heavy-duty trucks above its weight limits and anything before 1984 |
| NHTSA vPIC | Makes and models by year for every vehicle type, free with no key | No size class; lists trailers, motorcycles and obscure makes that must be filtered out |
| NHTSA vPIC Canadian specifications (`GetCanadianVehicleSpecifications`) | Curb weight, overall length, width, height and wheelbase per trim, by year, make and model | Models sold only in the US may be missing |

EPA size classes split pickups (from 2008) and SUVs (from 2013) into small and standard at 6,000 lb GVWR; car classes are set by interior volume ([fueleconomy.gov](https://fueleconomy.gov/feg/info.shtml)). FuelEconomy.gov leaves out most vehicles over 8,500 lb GVWR, and NHTSA vPIC fills those gaps. The Canadian specifications were checked on 2026-10-17 against a 2019 Toyota RAV4 (3,369 to 3,754 lb by trim) and the 2025 Ford range, including F-250 to F-450 Super Duty and Transit ([vPIC API](https://vpic.nhtsa.dot.gov/api/)).

## Classification rules are data

Classification will be an ordered list of rules the owner can edit in the control app ([decision 0060](../decisions/0060-vehicle-classification-rules-are-data.md)). Each rule has conditions on any stored fact about a model and gives a vehicle class; the first rule that matches wins.

- **Facts a rule can use:** EPA size class, body type, GVWR where known, curb weight, overall length, width and height, wheelbase, seat rows, doors and cab.
- **Example rule:** "EPA small SUV weighing over 4,500 lb → Midsize SUVs".
- **Trims differ,** so a rule uses the model's range, or the trim matching its cab or seat rows. A model that straddles a threshold goes to the owner once, as a per-model override.

## Overrides win over the rules

- **A per-model override** beats every rule, such as Jeep Wrangler to Light Pickups & Offroad, and Suburban, Expedition and Sequoia to Fullsize SUVs & Minivans.
- **A per-vehicle override** covers one customer's lifted or modified vehicle.

## A rule change is previewed before it is saved

Before a rule change is saved, the control app will list every model that would change vehicle class. A saved change applies to new quotes only; booked jobs keep their price.

## Settings each vehicle class carries

Each vehicle class will carry its own settings: what its size variant measures (doors, cab, seat rows or none), whether customers can book it online or must ask for a quote, and its photo card. The launch values are in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml).

## How a vehicle will get its class

1. The launch rules start from the EPA size class: car classes map to Coupes & Sedans, small SUVs and wagons to Crossovers & Wagons, small pickups to Light Pickups & Offroad, standard SUVs to Midsize SUVs, minivans and vans to Fullsize SUVs & Minivans, and standard pickups to Fullsize Trucks.
2. Rules on weight and dimensions, and the overrides above, fix known mismatches.
3. NHTSA vPIC fills the gaps the EPA leaves, mainly 2500 and 3500 series trucks, with the Canadian specifications for their weights and dimensions.
4. A monthly job re-pulls the sources. New models the rules classify cleanly go live; ambiguous ones wait in a review queue for one click from the owner.
5. A vehicle not in the list, such as a pre-1984 classic, falls back to choosing from photo cards, one per vehicle class.

EPA size classes are coarser for older SUVs, so those lean more on the rules and overrides. Before launch the owner reviews the mapping for every vehicle in the job history.

## How the size variant will be set without asking

Each vehicle model will store its size rule: 1, 2 or 3 rows, or "ask".

- **Cars are priced by doors.** The EPA file records two-door and four-door body styles separately, and NHTSA's VIN records carry a door count.
- **Pickups are priced by cab.** Cab style is not part of year, make and model, so the customer is asked "regular cab, or extended or crew cab?" unless the model has one cab style.
- **Crossovers and midsize SUVs need a third-row flag.** No free source lists optional third rows cleanly: the EPA data has no seating field, and NHTSA's seat-row fields are per VIN and often blank. The flags will be seeded from NHTSA where it has data and from a prepared list for the rest; the owner checks the crossovers, midsize SUVs and pickups, and anything unknown is set to "ask".
- **The list improves itself.** When the owner corrects a vehicle's size on a job, the model's record is updated.

The door and seat-row data claims come from general knowledge of the datasets and are measured in Phase 2.

## Guarding against a wrong class

The customer sees the class with a "not right?" link, the owner sees the vehicle on every booking, and each correction becomes a rule.

## Possible future vehicle classes

- **Motorcycles** may become a vehicle class, from vPIC's motorcycle makes.
- **RVs and oversized vans** may become "ask for a quote" classes priced by hand. The pricing engine is structured so a class could later be priced another way, such as per foot of length; see [pricing.md](pricing.md).
