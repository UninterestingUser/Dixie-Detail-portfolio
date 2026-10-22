---
title: Vehicle catalog
summary: The years, makes and models the system knows, the facts it keeps per model year from the EPA, NHTSA vPIC, the Canadian specifications and the third-row list, and how imports never overwrite the owner.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-22
tags: [vehicles, catalog, phase-2]
related: [docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, docs/decisions/0074-nameplates-aliases-and-majority.md, data/vehicle-names.yaml, docs/decisions/0073-classification-per-model-year.md, docs/reference/vehicle-classification.md, data/third-row-seating.yaml, docs/operations/importing-vehicle-data.md, data/vehicle-data-import.yaml, data/integrations.yaml, docs/architecture/data-model.md]
---

# Vehicle catalog

The vehicle catalog is the list of vehicle models a customer can pick by year, make and model, with the facts about each model year that the classification rules read ([vehicle-classification.md](vehicle-classification.md)). It is loaded by the `import_vehicle_data` command ([../operations/importing-vehicle-data.md](../operations/importing-vehicle-data.md)) and follows [decision 0071](../decisions/0071-vehicle-facts-per-model-year-and-source.md).

## A vehicle model is what a customer picks

A **vehicle model** is one make and model, such as "Toyota RAV4", with the first and last model year it covers. Each of its model years gets a vehicle class and size variant from the classification rules and overrides ([vehicle-classification.md](vehicle-classification.md)). Each vehicle model has a vehicle type: "car, truck or van", or "motorcycle". Motorcycles are shown in the same year, make and model lists as cars, and are in the Motorcycles vehicle class ([decision 0072](../decisions/0072-motorcycles-class.md)).

A motorcycle and a car of the same name are different vehicle models.

## Names customers know

A vehicle model is named the way customers know it, from [data/vehicle-names.yaml](../../data/vehicle-names.yaml) ([decision 0074](../decisions/0074-nameplates-aliases-and-majority.md)):

- **The EPA's base model is the model name,** so "RAV4 AWD" and "RAV4 Hybrid AWD" are both the RAV4.
- **Except where a base model holds several nameplates.** The EPA files the Santa Fe Sport and Santa Fe XL under the Santa Fe, the Range Rover Sport, Velar and Evoque under the Range Rover, and the Grand Cherokee L, Atlas Cross Sport, RX 350L and 450hL, Outlander Sport and PHEV, Encore GX, Defender 90, 110 and 130, Yukon XL, Escalade ESV, Navigator L, Expedition MAX and EL, and the EQE and EQS SUVs the same way. The nameplate list splits each: an EPA row whose model name contains a nameplate's phrase, as whole words, belongs to that nameplate, and the rest stay with the base model. The EPA's model names are not used whole, because they carry trims, engines and packages ("GLE350 4matic", "F150 2.7L 2WD GVWR>6649 LBS").
- **One vehicle, one name.** Names are matched across sources on capitals and digits only, so the EPA's "F150" and vPIC's "F-150" are the same. The alias list adds the spellings that differ in more than that, and gives the name shown: "GLE" for the EPA's and vPIC's "GLE-Class", "F-150" for "F150" and "F-150 Lightning", "Wrangler" for "Wrangler/TJ", "ML" for "ML-Class" and "M-Class", "Mazda5" for the EPA's "5". It also holds the make spellings, such as RAM TRUCKS for Ram in the Canadian specifications.

The import, the third-row list and the booking lookup all use these names, and so will matching customers' vehicles to the catalog. When the file changes, the next import merges the catalog models that are now one vehicle and splits the base models, and lists each merge, rename and split in its report. A merge keeps the owner's model, with its name, where there is one, and moves every model year, override and customer's vehicle to the model kept. A model year a split moves to a nameplate leaves the base model, and overrides stay on the model they were set for.

The owner can split one make and model into several vehicle models by year range, such as two generations with different vehicle classes. The import then files each model year under the vehicle model whose range holds it.

## Model-year facts are kept per source

Each source keeps its own **model-year facts** record for each model year it lists, such as the EPA's record for the 2019 Toyota RAV4. The third-row list, [data/third-row-seating.yaml](../../data/third-row-seating.yaml), is a source too: `classify_vehicles` writes its seat rows for each catalog model year it covers, replacing the last run's. One source never overwrites another. A source lists a model year several times (the EPA once per engine and transmission, the Canadian specifications once per trim), so each fact is gathered across those rows:

| Fact | Kept as | Units | From |
| --- | --- | --- | --- |
| EPA size class | Every class listed, such as "Small Sport Utility Vehicle 2WD" and "4WD" | | EPA |
| Drive | Every drive listed | | EPA |
| Body styles | Two-door, four-door, hatchback, or "unknown" | | EPA |
| Passenger and luggage volume | Lowest and highest | cubic feet | EPA |
| Source vehicle type | vPIC's own types, such as Truck or Motorcycle | | vPIC |
| Cab styles | Regular, extended and crew, from the trim names, such as "DOUBLE CAB" or "SUPERCREW" | | Canadian specifications |
| Seat rows | The numbers of seat rows sold: [2], [3], or [2, 3] for an optional third row | | The third-row list; NHTSA has none loaded |
| GVWR | Lowest and highest | pounds | No source yet; for the owner or a later source |
| Curb weight | Lowest and highest | pounds | Canadian specifications |
| Length, width, height, wheelbase | Lowest and highest | inches, to a tenth | Canadian specifications |

Each record also keeps the source's own ids (EPA vehicle ids, vPIC make and model ids, or the Canadian trim names), how its rows spread across each fact (rows per EPA size class, each trim's curb weight), which the classification rules use to go by the majority, and when it was first and last seen. A record the source stops listing is kept, and its "last seen" date shows when the source last listed it.

## How body styles are worked out

The EPA has no door field. The EPA lists passenger and luggage volume separately for two-door cars, four-door cars and hatchbacks. A body style is recorded when its passenger or luggage volume is not zero. When all six volumes are zero across the model year, as they are for pickups, vans and most SUVs, the body style is "unknown". Cars are priced by doors ([pricing.md](pricing.md)), so this is the fact the Coupes & Sedans size rule will use.

## Where each source's models come from

- **EPA FuelEconomy.gov** gives every car, SUV, van and light pickup from 1984 to the next model year.
- **NHTSA vPIC** fills the gaps for the truck and van makes listed in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml), chiefly pickups and vans over 8,500 lb GVWR such as the F-250, Silverado HD and Sprinter. A vPIC model that the EPA already has under another spelling is matched to it; the rest are added with source NHTSA. vPIC also gives the motorcycle models for the motorcycle makes listed there.
- **The Canadian specifications** add curb weight, dimensions and pickups' cab styles to models already in the catalog. They never add a model. A trim name's cab words are read as regular (REG CAB, SINGLE CAB), extended (SUPERCAB, DOUBLE CAB, KING CAB, QUAD CAB and the like) or crew (CREW CAB, SUPERCREW, CREWMAX, MEGA CAB).

## How Canadian rows are matched

A Canadian row names the model and trim together, such as "RAV4 AWD LE / XLE 4DR SUV". It is matched to the catalog model of the same make and model year whose whole name begins it and ends where one of its words ends: "RAV4" here, and "3 Series" for "3-SERIES 330i". The longest such name wins, so "F-250 SUPER DUTY" goes to the F-250, not the F-150.

A row is left for the owner, and listed in the import's report, when no name matches, when two names match equally, or when the name goes on with a series number such as 1500, 2500HD or HD ("SILVERADO 2500HD" against "Silverado"), because that row may be a heavier model. Guessing would put one model's weight on another and could move it to the wrong vehicle class.

## The import never overwrites the owner

A vehicle model with source "owner" keeps its make, model and years whatever the sources say; their facts are recorded beside it. A model-year facts record with source "owner" holds the owner's own figures, and no import ever changes it. This holds for every later step that imports vehicle data.

## Each import run is recorded

Every run of `import_vehicle_data` records, per source, when it started and ended, whether it was a dry run, its counts (models and model years added, changed and unchanged, unmatched and rejected rows, files downloaded) and whether it succeeded, with the reason when it failed. The monthly refresh will use these records.
