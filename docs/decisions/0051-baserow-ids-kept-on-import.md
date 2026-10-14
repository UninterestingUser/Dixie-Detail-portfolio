---
id: 51
title: "Imported records keep their Baserow ids so the import can be re-run before launch"
summary: "Every imported customer, vehicle and appointment keeps its Baserow row id, so the import can be re-run on a newer export before launch without making duplicates."
date: 2026-10-14
area: migration
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/data-migration.md, docs/decisions/0036-baserow-import.md]
---

# 0051: Imported records keep their Baserow ids so the import can be re-run before launch

**Status:** accepted · **Date:** 2026-10-14 · **Area:** migration

## Context

The Baserow import is built in Phase 1 and run before launch (decision 0036). Between the first test import and launch, the owner keeps using Baserow, and new jobs and corrections arrive. Matching customers again by name or phone is unreliable, and some customers have no phone number.

## Decision

- Each imported customer, vehicle and appointment stores the id of the Baserow row it came from, unique within its table, and empty for records created in the app.
- The import finds existing records by that id. Running it again with a newer export updates what was imported before and adds what is new, never duplicating a record.
- The import can be run as often as needed before launch. The last run before launch is the one that counts; after it, Baserow is retired.

## Alternatives considered

- **Import once into an empty database.** Any later fix would need the database emptied and the import run again.
- **Match by name or phone number.** Unreliable with shared numbers, spelling fixes and customers without a phone.

## Consequences

The Baserow ids stay on the records after launch as a reference to the old system. Until the final run, Baserow and the corrections list are the place to fix imported records: a re-run overwrites imported fields with the export's values, so a correction made only in the app would be lost.
