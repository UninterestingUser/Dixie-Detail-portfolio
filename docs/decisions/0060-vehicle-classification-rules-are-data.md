---
id: 60
title: "Vehicle classification rules are data the owner edits"
summary: "Classification is an ordered list of owner-editable rules on stored vehicle facts, first match wins, with per-model and per-vehicle overrides, a preview before saving and per-class settings."
date: 2026-10-17
area: vehicles
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: [docs/decisions/0082-size-based-vehicle-classes.md]
related: [docs/reference/vehicle-classification.md, data/vehicle-classes.yaml, data/integrations.yaml, docs/decisions/0016-size-from-vehicle-data.md, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md]
---

# 0060: Vehicle classification rules are data the owner edits

**Status:** superseded by [0082](0082-size-based-vehicle-classes.md) for the six body-type classes, applied by `apply_size_classes` ([0083](0083-applying-the-size-based-classes.md)); rules as data, overrides and the preview stand · **Date:** 2026-10-17 · **Area:** vehicles

## Context

Decisions 0016 and 0029 set where vehicle data comes from and that the size variant comes from it. The Phase 2 design mapped EPA size classes to vehicle classes with override rules, but did not say how the rules are written, what facts they can use, or how a rule change reaches existing quotes. Vehicle classes and size variants are already records (Phase 1 Step 2). The owner settled the rest on 2026-10-17. The six-class structure stays.

## Decision

1. **Rules are data.** Classification is an ordered list of rules the owner can edit. Each rule has conditions on any stored fact (EPA size class, body type, GVWR where known, curb weight, overall length, width and height, wheelbase, seat rows, doors, cab) and gives a vehicle class; the first match wins. Example: "EPA small SUV weighing over 4,500 lb → Midsize SUVs".
2. **Overrides win.** A per-model override beats every rule; a per-vehicle override covers one customer's lifted or modified vehicle.
3. **Preview before saving.** A rule change lists every model that would change class. It applies to new quotes only; booked jobs keep their price.
4. **Vehicle classes carry settings:** what the size variant measures (doors, cab, seat rows or none), whether customers can book the class online or must ask for a quote, and its photo card.
5. **Room for another price basis.** The pricing engine (Phase 1 Step 3) is structured so a class could later be priced another way, such as per foot of length for RVs. Only the fixed price list is built now.

Facts behind the rules:

- Booking stays year, make and model. VINs are not used for pricing; the owner only sees a VIN on site.
- EPA size classes split pickups (from 2008) and SUVs (from 2013) into small and standard at 6,000 lb GVWR; car classes are set by interior volume. FuelEconomy.gov leaves out most vehicles over 8,500 lb GVWR; NHTSA vPIC fills those gaps.
- vPIC's `GetCanadianVehicleSpecifications` gives curb weight, overall length, width, height and wheelbase per trim by year, make and model. Checked on 2026-10-17 against a 2019 Toyota RAV4 (3,369 to 3,754 lb by trim) and the 2025 Ford range, including F-250 to F-450 Super Duty and Transit. Models sold only in the US may be missing.
- Trims differ, so a rule uses the model's range, or the trim matching its cab or seat rows. A model that straddles a threshold goes to the owner once, as a per-model override.

## Alternatives considered

- **A fixed EPA-class mapping in code with a short override list.** Every new edge case would need a code change, and the owner could not see the effect of a change before making it.
- **Classify by VIN.** Customers book by year, make and model and rarely know their VIN; the owner sees it only on site.

## Consequences

Phase 2 builds the rule list, the preview and the class settings, and adds vPIC's Canadian specifications as a data source. Motorcycles may become a vehicle class later, from vPIC's motorcycle makes; RVs and oversized vans could become "ask for a quote" classes priced by hand.
