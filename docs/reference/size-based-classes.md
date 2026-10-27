---
title: Size-based vehicle classes
summary: The five vehicle classes by box volume the owner chose on 2026-10-26, their lines, rules and seat rows, the EPA size class fallback, and the dry run that previews them.
audience: [owner, staff, developer]
visibility: internal
status: draft
updated: 2026-10-26
tags: [vehicles, classification, pricing, phase-2]
related: [docs/decisions/0082-size-based-vehicle-classes.md, data/size-classes.yaml, docs/reference/vehicle-classification.md, docs/operations/classifying-vehicles.md, data/third-row-seating.yaml, data/vehicle-classes.yaml]
---

# Size-based vehicle classes

On 2026-10-26 the owner decided to class cars, wagons, crossovers, SUVs and minivans by measured size instead of body type ([decision 0082](../decisions/0082-size-based-vehicle-classes.md)). This page is a draft: the size-based classes are only previewed so far, and the live classes are still those in [vehicle-classification.md](vehicle-classification.md). When the classes are applied and priced, this page becomes current and replaces the body-type parts of that one. The classes, lines and rules are in [data/size-classes.yaml](../../data/size-classes.yaml).

## Why the size-based classes replace the body types

The EPA size class proved unreliable for pricing. Two-wheel-drive small crossovers are EPA cars or station wagons, so one model landed in two classes by drive. The Nissan Murano changed EPA label between generations. Battery weight puts small electric crossovers over the EPA's 6,000 lb rating line. What a detail takes depends on how big the vehicle is, so box volume decides.

## Box volume

Box volume is length × width × height ÷ 1,728, in cubic feet: a rough measure of bulk, not cargo space. Each dimension is the median of the model year's trims, from the owner's own figures where there are any, otherwise the Canadian specifications. A model year with no dimensions takes the box volume of the nearest measured model year of the same model, the newer on a tie, and says "inherited from" that year. `classify_vehicles` saves each model year's box volume each time it applies the rules.

## The size-based classes and their lines

The rules are tried in order and the first that holds gives the class. A model year exactly on a line belongs to the class above it: 490.0 cubic feet is Medium, 489.9 is Small.

| Order | Class | Rule | Booking |
| --- | --- | --- | --- |
| 1 | Motorcycles | Every motorcycle, unchanged | Online |
| 2 | Fullsize Trucks and Light Pickups | Pickups, identified as today, keeping the split | Online |
| 3 | Full-size Vans | 865 cubic feet and up | Ask for a quote |
| 4 | Full-size | 700 to under 865 | Online |
| 5 | Large | 580 to under 700 | Online |
| 6 | Medium | 490 to under 580, and every always-three-row vehicle under 490 | Online |
| 7 | Small | Under 490 | Online |

The lines are settings in [data/size-classes.yaml](../../data/size-classes.yaml), and the rules name them, so moving a line is one edit. The three-row floor counts only a model year the third-row data marks "always" three rows; an optional third row does not lift a small vehicle into Medium.

## Pickups in the size-based classes

Pickups keep their rules and their price by cab style: heavy pickups the EPA leaves out and EPA standard pickups are Fullsize Trucks; EPA small pickups are Light Pickups, the new name of Light Pickups & Offroad. The Hyundai Santa Cruz is named in its own rule, because the EPA lists every Santa Cruz as a small SUV. The Jeep Wrangler and the other models the old overrides put with the pickups are classed by size. A pickup size line may come later; the dry run's pickup ladder is there to place it.

## Seat rows, the size variant of the size-based classes

Every size-based class except Full-size Vans is priced by seat rows: one row for an EPA Two Seater, three when the third-row data says "always", asked when it says "optional", and otherwise two. Doors are no longer used. Full-size Vans has one price, quoted by hand.

## Models with no measurements

A model with no dimensions in any year takes the class where most measured model years of its EPA size class land, the EPA size class fallback. The dry run prints that table. A model with no dimensions and no EPA size class waits in the review queue, as any model year no rule matches does.

## What the size-based classes leave behind

The old model overrides, review queue decisions and approvals name the old classes and are not carried forward. The size rules replace the full-size SUV override list and the always-three-row SUV rule. When the classes are applied, every approval will be cleared and the old classes retired, not deleted.

## Customers' vehicles in the size-based classes

A linked vehicle with a year takes its model year's new class. One with no year gets a class only when every model year of its model has the same one; otherwise the year is needed. A vehicle not linked to the catalog gets a proposed class from its recorded class, for the owner to review: Coupes & Sedans to Small, Crossovers & Wagons to Medium, Midsize SUVs to Large, Fullsize SUVs & Minivans to Full-size (Large for a minivan), and pickups and motorcycles unchanged.

## Previewing the size-based classes

`classify_vehicles --scheme size --dry-run` classifies the whole catalog in memory with these rules and prints the result, changing nothing ([../operations/classifying-vehicles.md](../operations/classifying-vehicles.md#previewing-the-size-based-classes)). It creates no class or pricebook record: Small, Medium, Large, Full-size and Full-size Vans exist only in memory until they are applied. Prices for them will be added to `data/price-matrix.csv` and published as a new pricebook version then.
