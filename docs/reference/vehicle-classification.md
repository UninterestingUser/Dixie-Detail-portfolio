---
title: Vehicle classification
summary: How a year, make and model becomes a vehicle class and size variant, from EPA and NHTSA data, owner-editable rules, overrides, a third-row list and a review queue, and the lookup the booking form uses.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-22
tags: [vehicles, classification, phase-2]
related: [docs/decisions/0073-classification-per-model-year.md, docs/decisions/0072-motorcycles-class.md, docs/decisions/0060-vehicle-classification-rules-are-data.md, docs/reference/vehicle-catalog.md, docs/operations/classifying-vehicles.md, data/vehicle-classes.yaml, data/third-row-seating.yaml, data/integrations.yaml, docs/reference/pricing.md, docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md, docs/decisions/0016-size-from-vehicle-data.md]
---

# Vehicle classification

The customer picks year, make and model, and the system gives one of the seven vehicle classes and, where it can, the size variant, without asking. Booking stays year, make and model: VINs are not used for pricing, because the owner sees a VIN only on site. The classes and their settings are in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml); classes and size variants are records the owner can change (Phase 1).

This is built in Phase 2 Step 2 ([decision 0073](../decisions/0073-classification-per-model-year.md)). The `classify_vehicles` command applies the rules and overrides to every model year in the vehicle catalog ([vehicle-catalog.md](vehicle-catalog.md)) and stores each one's answer; how to run it is in [../operations/classifying-vehicles.md](../operations/classifying-vehicles.md). The booking form reads that stored answer through one lookup, described below; it uses it from Phase 3.

## Data sources

| Source | What it gives | Limits |
| --- | --- | --- |
| EPA FuelEconomy.gov | Year, make and model menus from 1984 to the next model year, the EPA size class, drive, passenger and luggage volume, and body styles worked out from the volumes | Leaves out heavy-duty trucks above its weight limits and anything before 1984; no door, seat, weight or size fields |
| NHTSA vPIC | Makes and models by year for every vehicle type, free with no key | No size class; matches make names loosely, so the import asks only for the makes listed in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml) and accepts only their vPIC names |
| NHTSA vPIC Canadian specifications (`GetCanadianVehicleSpecifications`) | Curb weight, overall length, width, height and wheelbase per trim, by year and make, and the cab style a pickup's trim name gives, such as "DOUBLE CAB" | Models sold only in the US may be missing; model and trim are one name, matched to the catalog only where the match is clear |
| The third-row list, [data/third-row-seating.yaml](../../data/third-row-seating.yaml) | Whether each crossover and midsize SUV sold in the US since 2010 has a third row always, optionally or never, by model year range, checked by the owner | Only crossovers and midsize SUVs from 2010 |

EPA size classes split pickups (from 2008) and SUVs (from 2013) into small and standard at 6,000 lb GVWR; car classes are set by interior volume ([fueleconomy.gov](https://fueleconomy.gov/feg/info.shtml)). FuelEconomy.gov leaves out most vehicles over 8,500 lb GVWR, and NHTSA vPIC fills those gaps. The Canadian specifications were checked on 2026-10-17 against a 2019 Toyota RAV4 (3,369 to 3,754 lb by trim) and the 2025 Ford range, including F-250 to F-450 Super Duty and Transit ([vPIC API](https://vpic.nhtsa.dot.gov/api/)). No source loaded gives GVWR, or seat rows from NHTSA: NHTSA's seat-row fields are per VIN and often blank.

## Classification rules are data

Classification is an ordered list of rules ([decision 0060](../decisions/0060-vehicle-classification-rules-are-data.md)). Each rule is a record with a position, a name, its conditions, the vehicle class it gives, and whether it is active. For each model year the active rules are tried from the lowest position up, and the first whose conditions all hold gives the class. The launch rules are in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml) and are seeded once, on the first run of `classify_vehicles`; after that the rules in the database are the owner's, edited in the Django admin until a control-app screen exists. A rule's conditions are checked when it is saved there.

A rule's conditions map a fact to what it must be. For example, "EPA small SUV weighing over 4,500 lb → Midsize SUVs" is:

```json
{"epa_size_class": ["Small Sport Utility Vehicle 2WD", "Small Sport Utility Vehicle 4WD"], "curb_weight": {"over": 4500}}
```

### Facts a rule can use

| Fact | Condition | From |
| --- | --- | --- |
| `vehicle_type` | A list: `vehicle` (car, truck or van) or `motorcycle` | The vehicle model |
| `make`, `model` | A list of names. A model matches a name it is or begins with in whole words, so "ProMaster" matches "ProMaster 2500". Names are compared on capitals and digits only | The vehicle model |
| `year` | `{"from": 2013, "to": 2019}`, either end optional | The model year |
| `epa_size_class`, `drive`, `body_style` | A list of values | EPA |
| `cab_style` | A list: `regular`, `extended`, `crew` | Canadian specifications |
| `seat_rows` | A list of numbers of rows, such as `[3]` | The third-row list, then NHTSA |
| `source_vehicle_type` | A list of vPIC's types, such as `Truck` or `Multipurpose Passenger Vehicle (MPV)` | vPIC |
| `gvwr`, `curb_weight` | `{"over": 4500}` and/or `{"up_to": 6000}`, in pounds | Canadian specifications (curb weight); no source yet (GVWR) |
| `length`, `width`, `height`, `wheelbase` | The same, in inches | Canadian specifications |
| `passenger_volume`, `luggage_volume` | The same, in cubic feet | EPA |

In a list, `none` matches a model year that no source gives a value for, such as a vPIC truck the EPA does not list.

### How a condition is tested

- **Every trim must match.** The catalog keeps each fact as a set or a range across a model year's trims, so a condition holds when it holds for all of them: all of the model year's EPA size classes are in the list, or its whole curb weight range is over the threshold. It fails when it holds for none.
- **A fact no source gives fails** the condition. An older SUV with no curb weight matches neither weight rule.
- **The owner's own figures come first.** Where the owner has recorded a fact for a model year, it is used and nothing else is read. Otherwise every source that gives the fact is read, and they must agree, except seat rows, which come from the third-row list first and NHTSA only where the list has nothing.

### The launch rules

The launch rules start from the EPA size class and add weight, dimension and name rules for the known mismatches, in this order:

1. **Motorcycles:** every model with vehicle type motorcycle ([decision 0072](../decisions/0072-motorcycles-class.md)).
2. **Full-size vans the EPA leaves out**, by name (Express, Savana, Transit, Sprinter, ProMaster and others) with no EPA size class → Fullsize SUVs & Minivans.
3. **Heavy pickups the EPA leaves out:** a vPIC truck with no EPA size class, such as the F-250, Silverado HD and Ram 2500 → Fullsize Trucks.
4. **Older minivans** the EPA lists as station wagons or special purpose vehicles, by name (Caravan, Odyssey, Sienna and others) → Fullsize SUVs & Minivans.
5. **Standard SUVs longer than 215 inches**, such as the Yukon XL and Escalade ESV → Fullsize SUVs & Minivans.
6. **Small SUVs over 4,500 lb** → Midsize SUVs.
7. **Older SUVs over 4,500 lb** and 8. **up to 4,500 lb**: before 2013 the EPA does not split SUVs into small and standard, so curb weight decides between Midsize SUVs and Crossovers & Wagons.
9. to 14. **The EPA mapping:** car classes to Coupes & Sedans, small SUVs and station wagons to Crossovers & Wagons, small pickups to Light Pickups & Offroad, standard SUVs to Midsize SUVs, minivans and vans to Fullsize SUVs & Minivans, and standard pickups to Fullsize Trucks.

Trucks above the 350 series stay in Fullsize Trucks, and full-size and fleet vans in Fullsize SUVs & Minivans, until an Oversized Vans & Trucks class exists.

## Overrides win over the rules

- **A model override** beats every rule, such as Jeep Wrangler to Light Pickups & Offroad, and Suburban, Expedition and Sequoia to Fullsize SUVs & Minivans (the launch overrides, seeded with the launch rules). It covers the model's years from one year to another, or all of them; one for some years beats one for the whole model. It sets the class and either fixes the size variant, always asks it, or leaves it to the facts as for any vehicle of the class. Each records who set it, when, and an optional note.
- **A vehicle override** covers one customer's lifted or modified vehicle: the vehicle's own class and size variant, with who set them, when, and an optional note. It beats the model override and the rules.

`classify_vehicles` never changes an override, a customer's vehicle, or anything with source "owner".

## The review queue

A model year goes to the review queue instead of going live when:

- **no rule matches** it;
- **its trims straddle a rule's condition**, such as a curb weight range from 4,300 to 4,700 lb against "over 4,500 lb", or EPA size classes in two classes, such as a model sold as a sedan and a wagon; or
- **two sources disagree** about a fact the rule tests.

The queue names the rule and the reason. The owner settles a model year with a model override (the model "straddles a threshold", decision 0060) or a new rule, and the next run of `classify_vehicles` takes it out of the queue. A model year that was live and enters the queue, for example after new data, keeps its earlier class while it waits; a new one has no class, and the booking form shows the photo cards.

On the full EPA table with the 2024 vPIC and Canadian data, the launch rules leave 2,418 of 12,672 model years in the queue. Most are SUVs from before 2013 with no curb weight yet, and models the EPA lists in two size classes, such as the 2WD and 4WD Highlander either side of 6,000 lb GVWR.

## A rule change is previewed before it is applied

Saving a rule or an override changes nothing the customer sees until `classify_vehicles` applies the rules. `classify_vehicles --dry-run` prints the preview: every model year whose class or size variant would change, or that would enter or leave the review queue, with the old and new values and the rule or override responsible. The preview is a function the control app can call with a proposed set of rules and overrides, unsaved, when its rule screen is built. An applied change reaches new quotes only; booked jobs keep their price.

## How the size variant is set without asking

Each model year stores its size variant, or that the customer is asked. Each vehicle model has an `ask_size` flag, set when the booking form asks the size for any of its model years.

- **A class with one size variant always has it,** as Fullsize SUVs & Minivans is always three rows. A class with none, Motorcycles, has one price.
- **Cars are priced by doors.** The EPA has no door field, but its volumes give each model year's body styles ([vehicle-catalog.md](vehicle-catalog.md)): two-door is the 1 size, four-door the 2. A model year sold as both, and a hatchback, whose doors the EPA does not give, is asked.
- **Pickups are priced by cab.** The Canadian specifications' trim names give the cab style: regular cab is the 1 size, extended or crew cab the 2. A model year with one cab style is not asked; one with several, or none known, is.
- **Crossovers and midsize SUVs by a third-row flag.** Seat rows come from the owner-approved third-row list, then from NHTSA where it has data. "Always" is three rows, "never" is two, and "optional" or anything unknown is asked.

### The third-row list

[data/third-row-seating.yaml](../../data/third-row-seating.yaml) lists each crossover and midsize SUV by make, the names it was sold under and a model year range. Each run of `classify_vehicles` loads it as the third-row list's own model-year facts, one per catalog model year the range covers, replacing the last run's. Its makes and models are matched to the catalog on capitals and digits only, as the import matches names, with the import's make aliases. A row that matches no catalog model, or none of the model's catalog years, is listed in the report instead of guessed. On the 2024 data, 28 of 187 rows matched no model, mostly where the EPA writes the name differently, such as "GLE-Class" for the Mercedes-Benz GLE, or lists several models as one, such as the Land Rover "Range Rover".

## Settings each vehicle class carries

Each vehicle class carries its own settings: what its size variant measures (doors, cab style, seat rows or none), whether customers book it online or ask for a quote, and its photo card's caption. `load_pricebook` creates the classes with the launch values from [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml); after that they are edited in the Django admin. All seven launch classes are booked online.

## The lookup

`classify(year, make, model, answers=None)` in `app/vehicles/classification/lookup.py` gives:

- the **vehicle class**;
- the **size variant**, or the **question still to ask**: "Two doors or four doors?", "Regular cab, or extended or crew cab?" or "Does it have a third row of seats?", answered through `answers` (`{"doors": 4}`, `{"cab": "regular"}`, `{"third_row": True}`);
- the class's **price basis** and the model's **vehicle type**;
- **how the answer was reached**: a rule, a model override, a vehicle override (when a customer's vehicle is given), or the review queue.

A year before 1984 (the first year of the catalog, in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml)), a model not in the catalog, and a model year waiting in the review queue with no class all return the **photo cards** instead: seven cards, one per vehicle class, Motorcycles among them, for the customer to choose from.

## Guarding against a wrong class

The customer sees the class with a "not right?" link, the owner sees the vehicle on every booking, and each correction becomes a rule or an override. The booking form shows these from Phase 3. When the owner corrects a vehicle's size on a job, the model's record will be updated, from Phase 3. Before launch the owner reviews the classes for every vehicle in the job history.

EPA size classes are coarser for older SUVs, so those lean more on the rules and overrides. A monthly job will re-pull the sources and reclassify (Phase 2 Step 5): new model years the rules classify cleanly go live, and the rest wait in the review queue.

## Possible future vehicle classes

- **Oversized Vans & Trucks:** full-size and fleet vans, and trucks above the 350 series. Until it exists they stay in Fullsize SUVs & Minivans and Fullsize Trucks.
- **RVs:** exterior only, priced per foot of length, which needs a new price basis. The pricing engine is structured so a class can be priced another way; see [pricing.md](pricing.md).
- **Boats:** a custom quote by size and work, outside the vehicle catalog.
