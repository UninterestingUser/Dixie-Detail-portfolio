---
id: 74
title: "Models are the nameplates customers know, and a rule goes by most of a model year's rows"
summary: "A nameplate list splits EPA base models and an alias list merges other spellings; a condition goes by a two-thirds majority of rows; unedited launch rules and overrides follow the data file."
date: 2026-10-22
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-22
supersedes: []
superseded_by: []
related: [data/vehicle-names.yaml, data/vehicle-classes.yaml, docs/reference/vehicle-catalog.md, docs/reference/vehicle-classification.md, docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, docs/decisions/0073-classification-per-model-year.md]
---

# 0074: Models are the nameplates customers know, and a rule goes by most of a model year's rows

**Status:** accepted · **Date:** 2026-10-22 · **Area:** vehicles

## Context

The owner's first `classify_vehicles --dry-run` showed four problems. The EPA's base model merges vehicles customers pick separately, such as the Santa Fe Sport and Santa Fe XL into the Santa Fe, several of which differ in seat rows. The vPIC gap fill added models the EPA already has under another spelling, such as EQB-Class beside EQB. Models such as the Highlander, Pilot and Silverado went to the review queue because a few of a model year's rows fell on the other side of a condition (decision 0073 required every row to agree). And the launch rules and overrides were seeded only on the first run, so a fix to them could not reach the server.

## Decision

1. **Keep the EPA base model and split it with a nameplate list,** in `data/vehicle-names.yaml`: a row whose EPA model name contains a nameplate's phrase, as whole words, belongs to that nameplate, such as "Range Rover Sport" for "New Range Rover Sport P360 MHEV". The import report lists every base model split.
2. **One alias list,** in the same file, gives each vehicle the name customers know and lists the other spellings of it ("GLE" for "GLE-Class", "F-150" for "F150" and "F-150 Lightning"), with the make spellings (RAM TRUCKS for Ram). The import, the third-row list and the booking lookup all use it, and so will matching customers' vehicles to the catalog. The import merges catalog models that are one vehicle, keeping the owner's model and its name where there is one, and lists every merge and rename.
3. **A condition is decided by the majority of a model year's rows:** it holds when at least two-thirds of them meet it and fails when two-thirds do not. Between, the model year waits in the review queue with the split. The share is `rule_settings.majority_share` in `data/vehicle-classes.yaml`. Each source's record keeps how its rows spread across each fact. Seat rows are what was sold, not trims, so an optional third row does not meet "three rows".
4. **Launch rules and overrides follow the data file.** Each one created from `data/vehicle-classes.yaml` records the entry it was made from. On each run an unedited one is brought in step with the file, a new entry is added, and one removed from the file is removed. One the owner edited, or deleted, is left alone and listed. The owner's own rules and overrides are never touched.

## Alternatives considered

- **Build model names from the EPA model name with drive and engine suffixes removed.** The EPA's model names carry trims, engines, payload packages and chassis codes, such as "GLE350 4matic", "F150 2.7L 2WD GVWR>6649 LBS" and "Suburban C1500 2WD"; stripping only drive and engine words would still leave dozens of false models for each vehicle, and every new EPA row could add more.
- **Lower the bar to "any row matches".** A model sold in two classes would silently take whichever rule comes first.
- **Reseed the launch set from scratch on each run.** Would overwrite the owner's edits.

## Consequences

The review queue on the 2024 test data drops from 2,418 to 1,777 model years, and every row of the third-row list matches a catalog model. A nameplate or spelling is added by editing `data/vehicle-names.yaml`; the next import splits or merges the catalog. Classifications of merged models are worked out again by the next `classify_vehicles` run. Rules and overrides seeded by the first version and never edited are marked by the migration as launch entries, so this change reaches them.
