---
id: 71
title: "Vehicle facts are kept per model year and per source"
summary: "Each source's facts about a vehicle model are kept per model year as sets and ranges across the source's rows, with the source's ids; motorcycles join the catalog; owner records are never overwritten."
date: 2026-10-22
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-22
supersedes: []
superseded_by: []
related: [docs/reference/vehicle-catalog.md, docs/reference/vehicle-classification.md, docs/operations/importing-vehicle-data.md, data/vehicle-data-import.yaml, data/integrations.yaml, docs/decisions/0029-vehicle-data-from-epa-and-nhtsa.md, docs/decisions/0060-vehicle-classification-rules-are-data.md]
---

# 0071: Vehicle facts are kept per model year and per source

**Status:** accepted · **Date:** 2026-10-22 · **Area:** vehicles

## Context

Decision 0029 chose the EPA and NHTSA vPIC as the vehicle data sources, and decision 0060 made classification an ordered list of owner-editable rules on stored facts. Phase 2 Step 1 loads those facts. Phase 1 had one vehicle model record per make and model over a range of years, with no room for facts. The sources disagree in shape: the EPA lists a model year once per engine and transmission, the Canadian specifications once per trim, and vPIC once per vehicle type. Trims of one model year differ in weight and size, and a model changes from one model year to the next.

## Decision

1. **The vehicle model stays the thing a customer picks and a vehicle class applies to.** It is one make and model, such as Toyota RAV4, with the range of years it covers.
2. **Facts are kept per model year and per source.** Each source has its own record for each model year it lists, with the EPA size classes, drives, body styles and the source's own vehicle types as sets, and passenger and luggage volume, GVWR, curb weight, length, width, height and wheelbase as a range (lowest and highest) across the source's rows. Each record keeps the source's own ids and when the record was first and last seen.
3. **The EPA's base model is the model name** ("RAV4" for "RAV4 AWD" and "RAV4 Hybrid AWD"). Names are matched across sources on capitals and digits only, so the EPA's "F150" and vPIC's "F-150" are one model.
4. **Body styles come from the EPA's volumes,** as it has no door field: two-door, four-door and hatchback when their passenger or luggage volume is not zero, and "unknown" when all are zero.
5. **Canadian specifications attach only to a clear match,** the catalog model whose whole name begins the Canadian model name. Anything else is listed for the owner, not guessed.
6. **Motorcycles join the catalog** from vPIC, marked with vehicle type motorcycle, and are shown in the same year, make and model lists as cars. They still have no vehicle class.
7. **The import never overwrites the owner.** A vehicle model with source "owner" keeps its name and years, and a model-year record with source "owner" is never touched. The sources' facts are recorded beside an owner's model.
8. **The makes to ask vPIC for live in data,** in `data/vehicle-data-import.yaml`, with the vPIC make names to accept, because vPIC matches make names loosely.
9. **Each run is recorded** with its start, end, counts and result, for the monthly refresh.

## Alternatives considered

- **One record per EPA row.** Keeps every engine and transmission, but a classification rule would have to reduce them to one answer every time, and the other sources have no such rows to join to.
- **One merged record per model year.** Simpler to read, but a later source would overwrite an earlier one, and the owner's corrections could not be kept apart from imported values.
- **Facts on the vehicle model itself.** Loses the change between model years, such as a redesign that adds weight or a third row.
- **Fuzzy name matching for the Canadian specifications.** Attaches more rows, but a wrong match, such as a Silverado 2500HD's weight on the light Silverado, would silently move a model to the wrong vehicle class.

## Consequences

Classification rules (Phase 2) read a model year's facts from each source and must say which source wins where two give a value, with the owner's own record first. No source in Step 1 gives GVWR, so those fields stay empty until a source or the owner fills them. Many Canadian rows are left unmatched where the names differ, such as "SILVERADO 1500" against the EPA's "Silverado"; the owner resolves those, and a later step can add name aliases. Some vPIC gap-fill models are commercial trucks or duplicates of EPA models under another name; the review queue handles them.
