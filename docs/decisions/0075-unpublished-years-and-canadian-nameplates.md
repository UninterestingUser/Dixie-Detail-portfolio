---
id: 75
title: "A model year the EPA has not published takes its model's nearest classified year, and Canadian trims split by nameplate"
summary: "Next year's models only vPIC lists take the class and size of the model's nearest classified year until the EPA data arrives; Canadian trims follow the nameplate list; the Jeep Wagoneer override starts in 2022."
date: 2026-10-23
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-23
supersedes: []
superseded_by: []
related: [docs/reference/vehicle-classification.md, docs/reference/vehicle-catalog.md, data/vehicle-classes.yaml, data/vehicle-names.yaml, docs/decisions/0073-classification-per-model-year.md, docs/decisions/0074-nameplates-aliases-and-majority.md]
---

# 0075: A model year the EPA has not published takes its model's nearest classified year, and Canadian trims split by nameplate

**Status:** accepted · **Date:** 2026-10-23 · **Area:** vehicles

## Context

The owner's second `classify_vehicles` dry run showed three problems. Next year's models, such as the 2027 F-150, RAV4, Highlander and Silverado, are listed by NHTSA vPIC before the EPA publishes them, so they have no EPA size class, no rule matches, and each went to the review queue; the monthly refresh would fill the queue with every new model year. The Jeep Wagoneer launch override covered every year, including the 1989 to 1990 Wagoneer, the old compact one. And the Mercedes-Benz EQE and EQS SUV facts were mixed in with the sedans: the Canadian specifications write both bodies as "EQE CLASS …", so every SUV trim's weight was matched to the sedan.

## Decision

1. **A model year the EPA has not published yet takes the class and size of the model's nearest classified year,** and the "how" line says so: "from the 2026 model year, rule 180: EPA standard pickups; the EPA has not published this year yet". A model year counts as unpublished when it has no EPA facts, the EPA lists earlier years of the model, and it is among the EPA's newest model years or later (`rule_settings.epa_unpublished_years`, 2 at launch, in `data/vehicle-classes.yaml`). A model override or a review queue decision for the year still wins. It is classified again, by the rules, when the EPA data arrives. A model the EPA never lists, such as the F-250, goes by the rules as before, and one with no classified year waits in the review queue.
2. **Canadian trims are split by the nameplate list,** as EPA rows are: a trim of a model `data/vehicle-names.yaml` splits goes to the nameplate its name names, so "EQE CLASS 350 4DR SUV" goes to the EQE SUV. The sedan spellings vPIC uses ("EQE-Class Sedan") are aliases of the EQE and EQS.
3. **The Jeep Wagoneer override starts in 2022,** like the Grand Wagoneer's.

## Alternatives considered

- **Leave unpublished years in the review queue.** The owner would settle the same models every year, for an answer the model's previous year already gives.
- **Carry the class to any year without EPA facts.** Old years the EPA skipped, such as a model's last year sold only to fleets, would take a class no one checked; the window keeps it to new years.
- **A rule per unpublished model.** One more thing to remove each year when the EPA data arrives.

## Consequences

New model years go live as soon as vPIC lists them, priced like the year before, and are checked against the rules when the EPA publishes them. The EQE and EQS SUVs need the Canadian specifications reloaded once (`import_vehicle_data --source canada`, from the cache) before `classify_vehicles` sees their weights.
