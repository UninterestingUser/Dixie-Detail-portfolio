---
id: 85
title: "Fixes from the first apply_size_classes dry run: seat rows, pickups in every year, full-size vans by nameplate, the Escalade"
summary: "Full-size and minivans are always three rows and one row only exists in Small; a pickup in any year is a pickup in all; named full-size vans are Full-size Vans; an Escalade override."
date: 2026-10-28
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: []
related: [docs/decisions/0083-applying-the-size-based-classes.md, docs/decisions/0082-size-based-vehicle-classes.md, data/size-classes.yaml, docs/reference/vehicle-classification.md, docs/operations/classifying-vehicles.md]
---

# 0085: Fixes from the first apply_size_classes dry run: seat rows, pickups in every year, full-size vans by nameplate, the Escalade

**Status:** accepted · **Date:** 2026-10-28 · **Area:** vehicles

## Context

The owner's first `apply_size_classes --dry-run` showed four kinds of wrong answer:

- seat rows the price book does not price, such as two-row model years in Full-size and two-seaters in larger classes;
- pickups whose early years no pickup rule caught, such as the 1995 to 1999 Tundra (Large) and the 2002 to 2003 Titan (Full-size);
- full-size vans that measure under the Full-size Vans line;
- the 2007 to 2014 Escalade, smoothed toward the class of its older years.

The price book does not change.

## Decision

1. **Seat rows.**
   - Full-size is always three rows.
   - An EPA minivan class is always three rows. So is a model with no EPA size class that is on the minivan list in `data/size-classes.yaml`.
   - One row exists only in Small: a two-seater that measures into a larger class counts as two rows.
2. **Pickups stay pickups in every year.** A model that a pickup rule catches in any model year is a pickup in all of them, except years settled by an override, a review queue decision or the photo cards. The 760 cubic foot line then decides between Light Pickups and Full-size Trucks, so a pickup is never Large or Full-size. A year with no box volume takes the class its pickup years mostly have. Older full-size pickups that measure under 760 cubic feet, such as a 2004 F-150, stay Light Pickups; that is the owner's decision.
3. **Full-size vans by nameplate.** The vans on the `full_size_vans` list are Full-size Vans in every model year, whatever they measure, by a rule tried before the pickup rules:
   - Express and Savana (cargo and passenger);
   - E-Series, E-150, E-250, E-350 and Econoline;
   - Ram Van and the B-series vans;
   - the G-series vans and Vandura;
   - Sprinter and eSprinter of every make;
   - Transit except Transit Connect, and ProMaster except ProMaster City;
   - NV1500, NV2500 and NV3500.

   Small vans (Transit Connect, ProMaster City, City Express, NV200, Metris) still go by size.
4. **The Escalade.** A model override puts the Cadillac Escalade 2007 to 2014 in Full-size, like the Tahoe and Yukon of those years.
5. **Backwards smoothing is reported.** The reports list, on their own, each smoothed run whose new class is not the class of its model's newest generation.

## Alternatives considered

- **Price two-row Full-size and one-row Medium and Large.** The owner kept the price book; those vehicles take the rows that are priced.
- **Turn a year into a pickup only when its neighbors are pickups.** Smoothing already does that for short runs; a whole early generation, like the 1995 to 1999 Tundra, needs the model-wide rule.
- **Raise the Full-size Vans line until every full-size van clears it.** It would move large SUVs too; the vans are known by name.

## Consequences

The price book check now counts only the rows a class is priced for, so the switch is no longer refused for Full-size or minivan seat rows. Rule positions move up by 10 after the new van rule. The owner reruns the dry run.
