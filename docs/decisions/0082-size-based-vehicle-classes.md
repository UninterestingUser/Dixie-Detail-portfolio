---
id: 82
title: "Cars, wagons, crossovers, SUVs and minivans are classed by measured size"
summary: "Five size-based classes by box volume (Small, Medium, Large, Full-size, Full-size Vans) replace the body-type classes; seat rows replace doors; pickups and motorcycles keep their rules."
date: 2026-10-26
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-26
supersedes: [docs/decisions/0014-cars-priced-by-doors.md, docs/decisions/0016-size-from-vehicle-data.md, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md, docs/decisions/0060-vehicle-classification-rules-are-data.md]
superseded_by: []
related: [data/size-classes.yaml, data/vehicle-classes.yaml, docs/reference/vehicle-classification.md, docs/operations/classifying-vehicles.md, docs/decisions/0074-nameplates-aliases-and-majority.md, docs/decisions/0015-crossover-three-row-price.md, docs/decisions/0073-classification-per-model-year.md, docs/decisions/0079-approval-list.md]
---

# 0082: Cars, wagons, crossovers, SUVs and minivans are classed by measured size

**Status:** accepted; takes effect when the size-based classes are applied · **Date:** 2026-10-26 · **Area:** vehicles

## Context

The body-type classes (Coupes & Sedans, Crossovers & Wagons, Midsize SUVs, Fullsize SUVs & Minivans) were assigned from the EPA size class, with a model override list for full-size SUVs and a rule that put every always-three-row SUV in Midsize SUVs. The vehicle size report showed that the EPA labels do not follow the size of the vehicle. Two-wheel-drive small crossovers are EPA cars or station wagons, so the same model lands in two classes by drive. The Nissan Murano changed EPA label between generations without changing much in size. Battery weight puts small electric crossovers over the EPA's 6,000 lb rating line, into the standard SUV class. What the owner works on is the size of the vehicle, so the owner decided on 2026-10-26 to class these vehicles by measured size instead.

## Decision

1. **Box volume is a stored fact.** For each model year, length × width × height ÷ 1,728 in cubic feet, each dimension the median of its trims, as the vehicle size report computes it. A model year with no dimensions takes the box volume of the nearest measured model year of the same model, the newer on a tie, and says "inherited from" that year.
2. **Five size-based classes replace the four body-type classes,** tried in this order after the motorcycle and pickup rules:
   - **Full-size Vans:** 865 cu ft and up. Asked for a quote, not booked online.
   - **Full-size:** 700 to under 865.
   - **Large:** 580 to under 700.
   - **Medium:** 490 to under 580, and every vehicle the third-row data marks "always" three rows under 490.
   - **Small:** under 490.

   A model year exactly on a line belongs to the class above it. The lines are settings in `data/size-classes.yaml`, not code.
3. **Pickups and motorcycles keep their rules.** Pickups are identified as before and keep the split between Light Pickups & Offroad, renamed **Light Pickups**, and Fullsize Trucks, priced by cab style. The Hyundai Santa Cruz, which the EPA lists as a small SUV, is named in a pickup rule. The Jeep Wrangler is no longer priced with the pickups. A pickup size line may come later, from the dry run's pickup ladder.
4. **Seat rows replace doors** as the size variant of every size-based class except Full-size Vans: one row for an EPA Two Seater, three for "always" and asked for "optional" in the third-row data, and otherwise two.
5. **A model with no measurements in any year** takes the class where most measured model years of its EPA size class land. With no dimensions and no EPA size class, it waits in the review queue, as any model year no rule matches does.
6. **The old model overrides, review queue decisions and approvals are not carried forward,** because they name the old classes. The size rules replace the full-size SUV override list and the always-three-row SUV rule, both launch entries in `data/vehicle-classes.yaml` added with the changes of [decision 0074](0074-nameplates-aliases-and-majority.md), which themselves had no decision record.
7. **First a dry run, then the switch.** `classify_vehicles --scheme size --dry-run` shows what the new rules give, the near-line models, every override and approval with its new class, and each customer's vehicle with its new class, and changes nothing. The classes are applied, and priced, in a later pull request.

This record replaces, once the classes are applied: the body-type classes and the EPA size class as the first guess at a class ([0060](0060-vehicle-classification-rules-are-data.md) point "the six-class structure stays", and [0029](0029-vehicle-data-from-epa-and-nhtsa.md)); cars priced by doors ([0014](0014-cars-priced-by-doors.md)); and the doors question of [0016](0016-size-from-vehicle-data.md). The rest of those decisions stands: rules are data the owner edits, with overrides and a preview (0060); the vehicle data comes from the EPA and NHTSA (0029); the size variant comes from the data and is asked only when needed (0016).

## Alternatives considered

- **Keep the body-type classes and add more overrides.** Every new crossover or electric vehicle the EPA labels oddly would need another override, and the classes would still split one model by drive.
- **Class by curb weight.** Batteries make electric vehicles heavy for their size, the problem the EPA's weight line already has.
- **Class by length alone.** A tall van and a long low sedan of the same length are very different jobs; box volume counts all three dimensions.
- **Use the EPA class only as a tiebreaker near a line.** The labels proved unreliable exactly where it would matter; they are kept only for models with no measurements at all.

## Consequences

The dry run lets the owner check the lines against real models and customers' vehicles before anything changes. When the classes are applied, every price for them must be set in `data/price-matrix.csv` and published as a new pricebook version; Light Pickups & Offroad is renamed; the old classes are retired, not deleted; and every approval is cleared. Booked jobs keep their price (decision 0059). Unlinked customer vehicles get a proposed class from their recorded class, for the owner to review.
