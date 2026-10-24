---
id: 78
title: "The two imported motorcycle jobs get the Motorcycles class and the Motorcycle Detail service, with their amounts as imported"
summary: "At the owner's request, link_vehicles gives the past motorcycle jobs the class and service decision 0072 added, keeping every amount and payment, and lists any amount that is not the Motorcycle Detail price."
date: 2026-10-24
area: migration
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-24
supersedes: []
superseded_by: []
related: [docs/decisions/0072-motorcycles-class.md, docs/decisions/0066-imported-payments-already-in-the-books.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0077-linking-vehicles-to-the-catalog.md, docs/reference/data-migration.md, docs/operations/linking-vehicles.md]
---

# 0078: The two imported motorcycle jobs get the Motorcycles class and the Motorcycle Detail service, with their amounts as imported

**Status:** accepted · **Date:** 2026-10-24 · **Area:** migration

## Context

The job history has two motorcycle jobs, done before motorcycles were on the price list. The Baserow import gave them no vehicle class and a custom line at the price charged, and decision 0072 kept them that way when it added the Motorcycles class and Motorcycle Detail. Reports by class and by service therefore miss them. Nothing else in the past changes when vehicles are linked (decision 0077), and the quoted price is the price of record (decision 0059). The owner asked on 2026-10-24 for the two jobs to be the exception.

## Decision

1. **`link_vehicles` gives each imported job of a vehicle linked to a motorcycle model,** imported with no class, the Motorcycles class on its lines and the Motorcycle Detail service on its first custom line, which becomes a service line named for it. The vehicle gets the Motorcycles class too. The class and service are the ones `data/vehicle-classes.yaml` and `data/services.yaml` name for motorcycles.
2. **Every amount and payment stays as imported,** because they are already in the books (decision 0066).
3. **The report lists any of the jobs whose amount is not the Motorcycle Detail price** in `data/price-matrix.csv` ($100 today), for the owner to decide.

This narrows the last consequence of decision 0072 ("the two imported motorcycle jobs keep their custom lines and no vehicle class"); the rest of 0072 stands.

## Alternatives considered

- **Leave them as custom lines (decision 0072).** Reports by class and service would keep missing the only motorcycle jobs.
- **Reprice them at $100.** Would change amounts already in GnuCash.

## Consequences

The lines' history records the change, with the reason. A rerun finds them done and leaves them alone. A Baserow import rerun recreates them as custom lines, and the next `link_vehicles` run gives them the class and service again.
