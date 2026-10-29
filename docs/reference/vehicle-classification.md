---
title: Vehicle classification
summary: How a year, make and model becomes one of the eight size-based vehicle classes and a size variant, from box volume, owner-editable rules, overrides and a review queue, and the booking lookup.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-29
tags: [vehicles, classification, phase-2]
related: [docs/decisions/0086-three-row-floor-after-seat-rows.md, docs/decisions/0085-size-class-fixes-after-the-first-dry-run.md, docs/decisions/0083-applying-the-size-based-classes.md, docs/decisions/0082-size-based-vehicle-classes.md, data/size-classes.yaml, docs/decisions/0081-monthly-vehicle-data-refresh.md, docs/decisions/0080-link-vehicles-follow-up.md, docs/decisions/0077-linking-vehicles-to-the-catalog.md, docs/decisions/0078-imported-motorcycle-jobs-get-their-class.md, docs/decisions/0079-approval-list.md, docs/operations/linking-vehicles.md, data/approval-spot-checks.yaml, docs/decisions/0075-unpublished-years-and-canadian-nameplates.md, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/operations/using-the-catalog-screens.md, docs/decisions/0074-nameplates-aliases-and-majority.md, docs/decisions/0073-classification-per-model-year.md, data/vehicle-names.yaml, docs/decisions/0072-motorcycles-class.md, docs/decisions/0060-vehicle-classification-rules-are-data.md, docs/reference/vehicle-catalog.md, docs/operations/classifying-vehicles.md, data/vehicle-classes.yaml, data/third-row-seating.yaml, data/integrations.yaml, docs/reference/pricing.md, docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md, docs/decisions/0016-size-from-vehicle-data.md]
---

# Vehicle classification

The customer picks year, make and model, and the system gives one of the eight vehicle classes and, where it can, the size variant, without asking. Booking stays year, make and model: VINs are not used for pricing, because the owner sees a VIN only on site. Cars, wagons, crossovers, SUVs, minivans and vans are classed by their measured size, their box volume; pickups by rule and the pickup size line; motorcycles by vehicle type ([decision 0082](../decisions/0082-size-based-vehicle-classes.md), applied by [decision 0083](../decisions/0083-applying-the-size-based-classes.md)). The classes and their settings are in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml), and the rules in [data/size-classes.yaml](../../data/size-classes.yaml); classes and size variants are records the owner can change (Phase 1).

This is built in Phase 2 Step 2 ([decision 0073](../decisions/0073-classification-per-model-year.md)). The `classify_vehicles` command applies the rules and overrides to every model year in the vehicle catalog ([vehicle-catalog.md](vehicle-catalog.md)) and stores each one's answer; how to run it is in [../operations/classifying-vehicles.md](../operations/classifying-vehicles.md). The booking form reads that stored answer through one lookup, described below; it uses it from Phase 3. Phase 2 Step 3 adds the control app's **Catalog** tab, where the owner looks vehicles up and changes the rules, overrides, class settings and review queue, each applied as it is confirmed ([decision 0076](../decisions/0076-catalog-screens-in-the-control-app.md), [../operations/using-the-catalog-screens.md](../operations/using-the-catalog-screens.md)). Phase 2 Step 4 links customers' vehicles to the catalog and adds the differences screen and the approval list, described below.

## Data sources

| Source | What it gives | Limits |
| --- | --- | --- |
| EPA FuelEconomy.gov | Year, make and model menus from 1984 to the next model year, the EPA size class, drive, passenger and luggage volume, and body styles worked out from the volumes | Leaves out heavy-duty trucks above its weight limits and anything before 1984; no door, seat, weight or size fields |
| NHTSA vPIC | Makes and models by year for every vehicle type, free with no key | No size class; matches make names loosely, so the import asks only for the makes listed in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml) and accepts only their vPIC names |
| NHTSA vPIC Canadian specifications (`GetCanadianVehicleSpecifications`) | Curb weight, overall length, width, height and wheelbase per trim, by year and make, and the cab style a pickup's trim name gives, such as "DOUBLE CAB" | Models sold only in the US may be missing; model and trim are one name, matched to the catalog only where the match is clear |
| The third-row list, [data/third-row-seating.yaml](../../data/third-row-seating.yaml) | Whether each crossover and midsize SUV sold in the US since 2010 has a third row always, optionally or never, by model year range, checked by the owner | Only crossovers and midsize SUVs from 2010 |

EPA size classes split pickups (from 2008) and SUVs (from 2013) into small and standard at 6,000 lb GVWR; car classes are set by interior volume ([fueleconomy.gov](https://fueleconomy.gov/feg/info.shtml)). FuelEconomy.gov leaves out most vehicles over 8,500 lb GVWR, and NHTSA vPIC fills those gaps. The Canadian specifications were checked on 2026-10-17 against a 2019 Toyota RAV4 (3,369 to 3,754 lb by trim) and the 2025 Ford range, including F-250 to F-450 Super Duty and Transit ([vPIC API](https://vpic.nhtsa.dot.gov/api/)). No source loaded gives GVWR, or seat rows from NHTSA: NHTSA's seat-row fields are per VIN and often blank.

## Classification rules are data

Classification is an ordered list of rules ([decision 0060](../decisions/0060-vehicle-classification-rules-are-data.md)). Each rule is a record with a position, a name, its conditions, the vehicle class it gives, and whether it is active. For each model year the active rules are tried from the lowest position up, and the first whose conditions all hold gives the class. The launch rules and model overrides are in [data/size-classes.yaml](../../data/size-classes.yaml), whose rules name the box-volume lines by name, so moving a line is one edit. Each one `classify_vehicles` creates from the file remembers the entry it came from, and each run brings an unedited one in step with the file, adds a new entry and removes one taken out of the file. One the owner has edited or deleted is left alone and listed in the report, and the owner's own rules are never touched ([decision 0074](../decisions/0074-nameplates-aliases-and-majority.md)). Rules are edited on the control app's rule screen, which writes each rule out in plain words and checks its conditions when it is saved; the Django admin checks them too.

A rule's conditions map a fact to what it must be. For example, "box volume at least 580 and under 700 cubic feet → Large" is:

```json
{"box_volume": {"at_least": 580, "under": 700}}
```

### Facts a rule can use

| Fact | Condition | From |
| --- | --- | --- |
| `vehicle_type` | A list: `vehicle` (car, truck or van) or `motorcycle` | The vehicle model |
| `make`, `model` | A list of names. A model matches a name it is or begins with in whole words, so "ProMaster" matches "ProMaster 2500". Names are compared on capitals and digits only | The vehicle model |
| `not_model` | A list of such names the model must not be or begin with; the pickup rules use it to leave out the vans | The vehicle model |
| `model_word` | A list of words or phrases the model's name contains as whole words, such as `HD`, `2500` or `Super Duty` | The vehicle model |
| `year` | `{"from": 2013, "to": 2019}`, either end optional | The model year |
| `epa_size_class`, `drive`, `body_style` | A list of values | EPA |
| `cab_style` | A list: `regular`, `extended`, `crew` | Canadian specifications |
| `seat_rows` | A list of numbers of rows, such as `[3]` | The third-row list, then NHTSA |
| `source_vehicle_type` | A list of vPIC's types, such as `Truck` or `Multipurpose Passenger Vehicle (MPV)` | vPIC |
| `gvwr`, `curb_weight` | `{"over": 4500}` and/or `{"up_to": 6000}`, in pounds, or `{"at_least": 4500}` and/or `{"under": 6000}`, where the number itself belongs to the upper side | Canadian specifications (curb weight); no source yet (GVWR) |
| `length`, `width`, `height`, `wheelbase` | The same, in inches | Canadian specifications |
| `passenger_volume`, `luggage_volume` | The same, in cubic feet | EPA |
| `box_volume` | The same, in cubic feet: length × width × height ÷ 1,728 from the median trim's dimensions, or the nearest measured model year's | Worked out from the Canadian specifications or the owner's figures ([decision 0082](../decisions/0082-size-based-vehicle-classes.md)) |

In a list, `none` matches a model year that no source gives a value for, such as a vPIC truck the EPA does not list.

Box volume is one figure per model year, so it never splits a model year's trims. A model year with no dimensions takes the box volume of the nearest measured model year of the same model, the newer on a tie, and the report says "inherited from" that year. A model with no measured year has none, and a box-volume condition fails for it. Each applied run saves every model year's box volume.

### How a condition is tested

- **Most of the rows decide.** Each source's record keeps how its rows spread across each fact: the EPA's engines and transmissions, the Canadian trims. A condition holds when at least two-thirds of a model year's rows meet it, such as 8 of 10 Silverado rows listed as standard pickups, and fails when two-thirds do not. In between, the model year waits in the review queue with the split, such as "3 of 6 rows (50%) meet it". The share is `rule_settings.majority_share` in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml) ([decision 0074](../decisions/0074-nameplates-aliases-and-majority.md)). A record with no spread, such as the owner's own figures, is decided on its whole set or range.
- **Seat rows are not trims** but what was sold, so an optional third row ([2, 3]) does not meet `seat_rows: [3]`, and never sends a model year to the queue.
- **A fact no source gives fails** the condition. A model year with no box volume matches no box-volume rule.
- **The owner's own figures come first.** Where the owner has recorded a fact for a model year, it is used and nothing else is read. Otherwise every source that gives the fact is read, and they must agree, except seat rows, which come from the third-row list first and NHTSA only where the list has nothing.

### The launch rules

The launch rules in [data/size-classes.yaml](../../data/size-classes.yaml) are tried in this order:

1. **Motorcycles:** every model with vehicle type motorcycle ([decision 0072](../decisions/0072-motorcycles-class.md)).
2. **Full-size vans by nameplate:** Full-size Vans in every model year, whatever they measure ([decision 0085](../decisions/0085-size-class-fixes-after-the-first-dry-run.md)): Express and Savana (cargo and passenger), E-Series, E-150, E-250, E-350 and Econoline, Ram Van and the B-series vans, the G-series vans and Vandura, Sprinter and eSprinter of every make, Transit except Transit Connect, ProMaster except ProMaster City, and NV1500, NV2500 and NV3500. The list is `full_size_vans` in [data/size-classes.yaml](../../data/size-classes.yaml).
3. **Heavy pickups the EPA leaves out:** a vPIC truck with no EPA size class whose name has a heavy-duty series (2500, 3500, HD, Super Duty, F-250 and the others listed in the rule), such as the F-250, Silverado HD and Ram 2500 → Full-size Trucks.
4. **Heavy pickups over 8,500 lb GVWR** the EPA leaves out → Full-size Trucks. No source gives GVWR yet; the owner's own figures can.
5. **EPA small pickups** → Light Pickups.
6. **Pickups the EPA lists as small SUVs:** the Hyundai Santa Cruz → Light Pickups.
7. **EPA standard pickups** → Full-size Trucks.
8. **Full-size Vans:** 865 cubic feet and up. Booked by quote.
9. **Full-size:** 700 to under 865.
10. **Large:** 580 to under 700.
11. **Medium:** 490 to under 580.
12. **Small:** under 490. A Small model year with three seat rows is lifted to Medium by the three-row floor, the last step below.

A model year exactly on a line belongs to the class above it: 490.0 cubic feet is Medium and 489.9 is Small. **Vans are identified before the pickup rules:** every pickup rule leaves out the models named in the vans list (ProMaster, Transit, Sprinter, Express, Savana, E-Series, NV, Metris and similar), so a van of a heavy-duty series is never a pickup. A full-size van named in the nameplate rule is a Full-size Van; small vans (Transit Connect, ProMaster City, City Express, NV200, Metris) are classed by size like any other vehicle. Trucks above the 350 series stay in Full-size Trucks until an Oversized Vans & Trucks class exists.

### The steps after the rules

These steps follow the rules, in this order (decisions [0083](../decisions/0083-applying-the-size-based-classes.md) and [0085](../decisions/0085-size-class-fixes-after-the-first-dry-run.md)):

1. **Pickups in every model year.** A model that a pickup rule catches in any model year is a pickup in all of them, so a pickup is never Large or Full-size: the 1995 to 1999 Tundra and 2002 to 2003 Titan, whose earlier years no pickup rule caught, are pickups like their later years. Overrides, review queue decisions and the photo cards are left alone. A year with no box volume takes the class its pickup years mostly have.
2. **The pickup size line.** A pickup a rule caught that has a box volume, its own or inherited, is a Light Pickup under 760 cubic feet and a Full-size Truck at 760 and up. A pickup with no box volume in any year keeps its rule's class, from its EPA label: small pickups are Light Pickups, standard pickups and heavy-duty trucks Full-size Trucks. The line is `pickup_line` in [data/size-classes.yaml](../../data/size-classes.yaml).
3. **The EPA size class fallback.** A model with no measurements in any year takes the class where most measured model years of its EPA size class land. With no dimensions and no EPA size class, it waits in the review queue.
4. **Smoothing.** A run of up to six model years between two runs of the same class takes that class, so a model does not flip class for a year or two at a line. Model overrides, review queue decisions and next year's models carried from the nearest year are never smoothed. Every report lists each smoothed run, and its "how" line names the rule that gave the class it replaced. The reports also list, on their own, each smoothed run whose new class is not the class of its model's newest generation, so a backwards smooth is easy to spot.

5. **The three-row floor.** Once seat rows are final, a Small model year with three seat rows is Medium with three rows, whatever made it three rows: the third-row data's "always", an EPA minivan class, or the minivan list ([decision 0086](../decisions/0086-three-row-floor-after-seat-rows.md)). So every three-row vehicle under 490 cubic feet, such as a 1984 to 1991 Dodge Caravan or a 2008 to 2009 Mazda5, is Medium. An optional third row does not count: the year stays Small and the size is asked. Model overrides and review queue decisions are left alone. The setting is `three_row_floor` in [data/size-classes.yaml](../../data/size-classes.yaml).

Older full-size pickups that measure under 760 cubic feet, such as a 2004 F-150, are Light Pickups: the owner's decision of 2026-10-28.

## Overrides win over the rules

- **A model override** beats every rule and every step after them, such as the 2022 to 2026 Audi Q4 e-tron to Medium. The launch overrides are the owner's in [data/size-classes.yaml](../../data/size-classes.yaml): the Audi Q4 e-tron 2022 to 2026 to Medium, the Porsche Cayenne 2026 to Large, the BMW iX 2026 to Medium, and the Cadillac Escalade 2007 to 2014 to Full-size, like the Tahoe and Yukon of those years. An override covers the model's years from one year to another, or all of them; one for some years beats one for the whole model. It sets the class and either fixes the size variant, always asks it, or leaves it to the facts as for any vehicle of the class. Each records who set it, when, and an optional note.
- **A vehicle override** covers one customer's lifted or modified vehicle: the vehicle's own class and size variant, with who set them, when, and an optional note. It beats the model override and the rules.
- **A review queue decision** settles one model year from the review queue: a class with its size fixed, always asked or from the facts, or the photo cards. A model override covering the year beats it; it beats the rules ([decision 0076](../decisions/0076-catalog-screens-in-the-control-app.md)).

`classify_vehicles` never changes an override the owner set or edited, a review queue decision, a customer's vehicle, or anything with source "owner". The body-type classes' rules, overrides, decisions and approvals were archived when the size-based classes were applied: kept for history, no longer used.

## Model years the EPA has not published yet

NHTSA vPIC lists next year's models, such as the 2027 F-150, RAV4, Highlander and Silverado, months before the EPA publishes them, so they have no EPA size class and no rule would match. Such a model year takes the class and size of the same model's nearest classified year, and the "how" line says so: "from the 2026 model year, rule 70: EPA standard pickups; the EPA has not published this year yet" ([decision 0075](../decisions/0075-unpublished-years-and-canadian-nameplates.md)). It counts as unpublished when it has no EPA facts, the EPA lists earlier years of the model, and it is among the EPA's two newest model years or later (`rule_settings.epa_unpublished_years` in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml)). A model override or queue decision for the year still wins. When the EPA data arrives, the rules classify it again. A model the EPA never lists, such as the F-250, goes by the rules as always, and one with no classified year waits in the review queue.

## The review queue

A model year goes to the review queue instead of going live when:

- **no rule matches** it;
- **its rows have no clear majority** on a rule's condition, such as a model sold as a sedan and a wagon in equal numbers, or a curb weight range from 4,300 to 4,700 lb against "over 4,500 lb" with no spread of trims to go by; or
- **two sources disagree** about a fact the rule tests; or
- **the monthly refresh held it**: the refresh would have changed the class or size of a model the owner relies on (see [The monthly refresh](#the-monthly-refresh)).

The queue names the rule and the reason, files it under one of the four reasons for filtering, and suggests a class: the class of the rule its trims straddle, or of the model's nearest classified year, with the size its facts give. The owner settles a model year from the control app's review queue, one at a time or many at once: accept the suggestion, pick another class and size, or send it to the photo cards. A model override (the model "straddles a threshold", decision 0060) or a new rule settles it too. A model year that was live and enters the queue, for example after new data, keeps its earlier class while it waits; a new one has no class, and the booking form shows the photo cards.

With the size-based classes, a model year waits in the queue mainly when its model has no measurements in any year and no measured model year shares its EPA size class, or it has neither; `apply_size_classes` and `classify_vehicles` report how many.

## The monthly refresh

On the first Sunday of each month, `dixie-vehicle-refresh.timer` reloads the vehicle data from the EPA, vPIC and the Canadian specifications with fresh downloads, then runs `classify_vehicles --refresh`, which classifies new model years with the size-based rules ([decision 0081](../decisions/0081-monthly-vehicle-data-refresh.md), [../operations/monitoring.md](../operations/monitoring.md)). Its log holds only the model years newly sent to the review queue and the one-line summary.

- **What the refresh changes on its own:** it adds new models and model years, which go live when the rules classify them cleanly; the rest wait in the review queue as usual, and a year the EPA has not published yet takes its model's nearest classified year. It updates facts, and changes the class of a model nothing protects.
- **What the refresh never changes:** the vehicle class or size variant of a model year that is already live, when its model has a model override, an approval on the approval list, or customers' jobs (every model in the approval list's job history). That model year goes to the review queue under "Held by the monthly refresh" and keeps its class meanwhile. The reason gives the old and the new class and size, such as "the monthly refresh would change this from Medium (two rows) to Large (two rows) (rule 100: Large); held because it is in the job history", and the suggestion is the new one. **Accept** takes the new class; picking the old one keeps it. For a model with a model override, change the override, which beats a queue decision.
- **A held model year stays held** until the owner settles it, even after the hold has cleared the model's approval. It leaves the queue by itself only if the facts change back.
- **Nothing is deleted.** A model or model year a source stops listing is kept, with the date the source last listed it ([vehicle-catalog.md](vehicle-catalog.md#a-model-a-source-stops-listing-is-kept)).

The hold applies only to the refresh. A rule, override or class setting changed in the control app, and `classify_vehicles` run by hand, apply the rules as they are, because the owner sees the preview first.

## A rule change is previewed before it is applied

A rule change on the control app's rule screen (adding, editing, moving, disabling or enabling a rule) shows its preview first: every model year whose class or size variant would change, or that would enter or leave the review queue, grouped by old and new class, with the rule or override responsible. Nothing changes until the owner confirms it; then it is saved and applied to the whole catalog at once. A change to what a class's size variant measures is previewed the same way. A model override, the third-row flag and a queue decision reach one model and apply at once. `classify_vehicles --dry-run` prints the same preview on the server. An applied change reaches new quotes only; booked jobs keep their price.

Every change is logged with who made it, when, and each model year it changed, before and after, and a model's screen shows every change that reached it.

## How the size variant is set without asking

Each model year stores its size variant, or that the customer is asked. Each vehicle model has an `ask_size` flag, set when the booking form asks the size for any of its model years.

- **Small, Medium, Large and Full-size are priced by seat rows** (decisions [0082](../decisions/0082-size-based-vehicle-classes.md) and [0085](../decisions/0085-size-class-fixes-after-the-first-dry-run.md)), decided in this order: Full-size is always three rows; an EPA minivan class, or a listed minivan with no EPA size class, is always three, so an Odyssey or Sienna is three rows; an EPA Two Seater is one row in Small and two in a larger class, so one row exists only in Small; otherwise three when the third-row data says "always", asked when it says "optional", and two. Doors are no longer used. Each class has the size variants the price book prices: Small one or two rows, Medium and Large two or three, Full-size three.
- **A class with one size variant always has it,** as Full-size is always three rows. A class with none, Full-size Vans and Motorcycles, has one price, and Full-size Vans is quoted by hand.
- **Pickups are priced by cab.** The Canadian specifications' trim names give the cab style: regular cab is the 1 size, extended or crew cab the 2. A model year with one cab style is not asked; one with several, or none known, is.
- **Seat rows come from the owner-approved third-row list,** then from NHTSA where it has data.

The price book check refuses a price book that leaves out a class and row count the rules give a model year, such as a two-row Medium ([pricing.md](pricing.md#the-price-book-check)).

### The third-row list

[data/third-row-seating.yaml](../../data/third-row-seating.yaml) lists each crossover and SUV sold since 2010 by make, the names it was sold under and a model year range. Each run of `classify_vehicles` loads it as the third-row list's own model-year facts, one per catalog model year the range covers, replacing the last run's. Its makes and models are matched to the catalog by the names in [data/vehicle-names.yaml](../../data/vehicle-names.yaml), as the import matches them ([vehicle-catalog.md](vehicle-catalog.md#names-customers-know)). A row that matches no catalog model, or none of the model's catalog years, is listed in the report instead of guessed. With the nameplates and aliases, every one of the list's 187 rows matches a catalog model on the 2024 data; 28 did not before.

## Settings each vehicle class carries

Each vehicle class carries its own settings: what its size variant measures (seat rows, cab style or none), whether customers book it online or ask for a quote, and its photo card: a caption, a few example models, and a photo, with a placeholder until the owner adds one. `load_pricebook` creates the classes with the launch values from [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml); after that they are edited on the control app's class settings screen, and size variants in the Django admin. Full-size Vans is booked by quote; the other seven classes are booked online.

The body-type classes, Coupes & Sedans, Crossovers & Wagons, Midsize SUVs and Fullsize SUVs & Minivans, are retired. A retired class is kept for history: past appointments and their quote lines keep the class they had. It is never offered on booking, quoting or the catalog screens, and never priced again. Light Pickups & Offroad is now Light Pickups, and Fullsize Trucks is Full-size Trucks, the same records renamed.

## The lookup

`classify(year, make, model, answers=None)` in `app/vehicles/classification/lookup.py` gives:

- the **vehicle class**;
- the **size variant**, or the **question still to ask**: "Regular cab, or extended or crew cab?" or "Does it have a third row of seats?", answered through `answers` (`{"cab": "regular"}`, `{"third_row": True}`);
- the class's **price basis** and the model's **vehicle type**;
- **how the answer was reached**: a rule, the pickup size line, the EPA size class fallback, smoothing, a model override, a review queue decision, the nearest classified year (a year the EPA has not published yet), a vehicle override (when a customer's vehicle is given), or the review queue, with a sentence saying which.

The make and model are matched by the names in [data/vehicle-names.yaml](../../data/vehicle-names.yaml), so "GLE-Class" finds the GLE. Where two catalog models of one name cover the year, such as a car and a motorcycle, the lookup prefers the car; linking customers' vehicles never makes that choice (below). A year before 1984 (the first year of the catalog, in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml)), a model not in the catalog, and a model year waiting in the review queue with no class, and one the owner sent to the photo cards, all return the **photo cards** instead: eight cards, one per offered vehicle class, Motorcycles among them, for the customer to choose from. Each card has the class name, its caption, its example models (Civic, Corolla, Camry, Accord and Crosstrek for Small, for example) and its photo, or a placeholder until the owner adds one. The Full-size Vans card asks the customer to send a photo for a quote.

## Customers' vehicles and the catalog

`link_vehicles` links each customer's vehicle to its catalog model ([decision 0077](../decisions/0077-linking-vehicles-to-the-catalog.md), [../operations/linking-vehicles.md](../operations/linking-vehicles.md)). It matches the year, make and model with the names in [data/vehicle-names.yaml](../../data/vehicle-names.yaml): make spellings such as "Chevy" and "Mercedes", the other spellings of a model, and the trim words a customer's model name may carry, such as "LE", "XLT" or "EX-L". The longest start of the model field that names a catalog model of the make, sold in the vehicle's year, wins, and only when every word after it is a trim word: "Silverado 1500 LT" is the Silverado, but "Silverado 2500HD" is not, because 2500HD is not a trim word. A word one of the model's nameplates uses is never dropped, so "Wagoneer S" is never the Wagoneer. Case and spacing never matter. Customer aliases name a vehicle the catalog files under another name or make, some for certain model years only: a 2015 "Dodge Ram" is the Ram 1500, because Ram became its own make for 2011, while a 2009 one is the Dodge. A vehicle with no year is linked by its make and model alone when the name fits one catalog model; it keeps its class, which depends on the year, and is not compared with the catalog until its year is filled in ([decision 0080](../decisions/0080-link-vehicles-follow-up.md)). A vehicle of a make that sells only motorcycles gets the Motorcycles class even with no model.

It never guesses. When two catalog models fit equally, such as a car and a motorcycle of one name, both are listed and the vehicle stays unlinked. A link fills a missing vehicle class, and a missing size variant the catalog fixes, but never changes the class or size a vehicle has, with one exception: `apply_size_classes` set every linked vehicle's class from the size-based classes, a vehicle with no year taking its model's newest generation and flagged so the year is confirmed at its next visit. A vehicle left in a retired class, because it is not linked or its model year has no class, waits on the **Differences** screen with a class proposed from its old one. Any other difference waits for the owner on the control app's **Differences** screen, where one tap keeps the imported class as the vehicle's own override, takes the catalog's, or gives every vehicle of the model that class with a model override. Past jobs keep their prices ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)), except the two imported motorcycle jobs, which get the Motorcycles class and the Motorcycle Detail service with their amounts as imported ([decision 0078](../decisions/0078-imported-motorcycle-jobs-get-their-class.md)).

## The approval list

The owner approves the class for every model on the control app's **Approvals** screen (decisions [0079](../decisions/0079-approval-list.md) and [0083](../decisions/0083-applying-the-size-based-classes.md)); approving the whole list was Phase 2's done test, passed on 2026-10-29. The list started over when the size-based classes were applied, and holds every model with the make and name of a vehicle in the job history, whether or not its vehicles have a year; the spot-check list in [data/approval-spot-checks.yaml](../../data/approval-spot-checks.yaml), some entries for certain model years only, such as the Tahoe before 2007; every model with model years from 2015 on within 5 cubic feet of a size line or the pickup line; and every model approved since. Each model shows as its year ranges, the consecutive model years with one class, size and "how" line; a model listed only for some years shows only the ranges that overlap them. Each range is approved or changed on its own; a change sets a model override for exactly those years. Each approval records who gave it and when. Any later change that alters an approved range, by its years, class, size or how, clears the approval, and the model shows again.

## Guarding against a wrong class

The customer sees the class with a "not right?" link, the owner sees the vehicle on every booking, and each correction becomes a rule or an override. The booking form shows these from Phase 3. When the owner corrects a vehicle's size on a job, the model's record will be updated, from Phase 3. Every model in the job history is on the approval list, and the owner approves each one again when a change clears its approval.

EPA size classes are coarser for older SUVs, so those lean more on the rules and overrides. The monthly refresh re-pulls the sources and reclassifies, and never changes the class of a model the owner relies on without asking ([The monthly refresh](#the-monthly-refresh)).

## The vehicle size report

The `vehicle_size_report` command gathered the facts for decision 0082: the stored dimensions of every model in the body-type classes and the review queue's cars, wagons and SUVs, with their size ranges and box volumes. It reads the body-type classes, so since the switch it finds only the review queue's model years; the `apply_size_classes` and `classify_vehicles` reports replace it ([../operations/classifying-vehicles.md](../operations/classifying-vehicles.md#vehicle-size-report)).

## Applying the size-based classes

`apply_size_classes --effective YYYY-MM-DD` switches the catalog from the body-type classes to the size-based ones in one transaction, so the classes and the prices never disagree ([decision 0083](../decisions/0083-applying-the-size-based-classes.md), [../operations/classifying-vehicles.md](../operations/classifying-vehicles.md#applying-the-size-based-classes)). It publishes the new price book, renames and retires classes, archives the old rules, overrides, review queue decisions and approvals, creates the size-based rules and overrides, classifies every model year, and sets each customer's vehicle's class. Every booked job keeps its quoted price; the owner decides each on the version's booked-job review. The owner ran it on 2026-10-28, so `classify_vehicles` and the monthly refresh use the size-based rules, and a second run says the classes are already applied.

## Possible future vehicle classes

- **Oversized Vans & Trucks:** trucks above the 350 series. Until it exists they stay in Full-size Trucks.
- **RVs:** exterior only, priced per foot of length, which needs a new price basis. The pricing engine is structured so a class can be priced another way; see [pricing.md](pricing.md).
- **Boats:** a custom quote by size and work, outside the vehicle catalog.
