---
id: 73
title: "Vehicle classification is applied per model year, with straddling and disputed facts sent to review"
summary: "Rules are records with conditions on stored facts, applied to each model year by classify_vehicles; trims that straddle a condition or sources that disagree send it to the review queue."
date: 2026-10-22
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-22
supersedes: []
superseded_by: []
related: [docs/reference/vehicle-classification.md, docs/operations/classifying-vehicles.md, data/vehicle-classes.yaml, data/third-row-seating.yaml, docs/decisions/0060-vehicle-classification-rules-are-data.md, docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, docs/decisions/0072-motorcycles-class.md]
---

# 0073: Vehicle classification is applied per model year, with straddling and disputed facts sent to review

**Status:** accepted · **Date:** 2026-10-22 · **Area:** vehicles

## Context

Decision 0060 made classification an ordered list of owner-editable rules on stored facts, with overrides, a preview and a review queue, but left how they are stored and applied to Phase 2. Decision 0071 keeps each source's facts per model year, as sets and ranges across trims. A model changes between model years: the Toyota Highlander has an optional third row from 2010 to 2013 and always has one from 2014, and the owner-approved third-row list (`data/third-row-seating.yaml`) is written by year range. A rule's conditions can name a year range. Pickups are priced by cab style, which no source lists as a field.

## Decision

1. **Rules are database records,** each with a position, a name, conditions and the vehicle class it gives, edited by the owner. The launch rules are seeded once from `data/vehicle-classes.yaml`. Conditions are a mapping of fact to value, checked when a rule is saved.
2. **Classification is applied per model year.** `classify_vehicles` applies the rules and overrides to every model year in the catalog and stores each one's vehicle class and size variant, or that the size is asked. The booking lookup reads the stored answer for the year the customer picked. A rule change reaches bookings only when `classify_vehicles` applies it, and `--dry-run` previews it.
3. **A condition holds when it holds for every trim.** All of a model year's EPA size classes must be in a rule's list, or its whole curb weight range over a threshold. A model year whose trims straddle a rule's condition goes to the review queue, as does one where no rule holds, and one where two sources disagree about a fact the rule tests.
4. **The owner's own record wins** for any fact, with no disagreement possible. Seat rows come from the third-row list first, then NHTSA, so the list is never in dispute.
5. **A model year in the review queue does not go live.** One that was live keeps its earlier class while it waits; a new one has none, and the booking form falls back to the photo cards.
6. **A model override may cover a year range.** One for some years beats one for the whole model. It sets the class, and fixes the size, always asks it, or leaves it to the facts. A per-vehicle override is the vehicle class and size variant on a customer's vehicle, marked with who set it, when and why; it beats both.
7. **Size variants come from facts.** Doors from the EPA's body styles (a hatchback's doors are not given, so it is asked). Cab style from the Canadian specifications' trim names, such as "DOUBLE CAB" or "SUPERCREW". Seat rows from the third-row list: always is three, never is two, and optional is asked. A class with one size variant always has it. Anything unknown is asked.
8. **The vehicle model keeps one flag, ask_size,** set when the booking form asks the size for any of its model years. The class and size variant fields the vehicle model had are removed; the migration turns any class set there by hand into a model override.

## Alternatives considered

- **Classify per vehicle model, across all its years.** One answer per model, but the Highlander would ask about a third row in every year, and the owner would have to split a model by years for each change the list records.
- **Evaluate the rules at booking time.** Always current, but a rule edit would reach the website before anyone saw its effect, and the review queue would have nothing to hold.
- **A condition holds when any trim matches.** Fewer reviews, but a model sold in two classes, such as a sedan and a wagon, would silently take whichever rule comes first.
- **Separate fields for each condition on the rule.** Easier to edit in a form, but every new fact would need a migration.

## Consequences

The first run puts many model years in the review queue: on the full EPA table with the 2024 vPIC and Canadian data, 2,418 of 12,672. Most are SUVs from before 2013, which the EPA does not split into small and standard and which have no curb weight yet, and models the EPA lists in two size classes, such as the 2WD and 4WD Highlander either side of 6,000 lb GVWR. The owner settles each one with a rule or a model override. Rules are edited in the Django admin until a control-app screen exists. Cab styles need the Canadian specifications reloaded once with `import_vehicle_data --source canada`.
