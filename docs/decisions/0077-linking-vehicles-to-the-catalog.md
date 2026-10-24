---
id: 77
title: "Customers' vehicles are linked to the catalog by name without guessing, and a class changes only on the owner's tap"
summary: "link_vehicles matches each vehicle by the names data file, with trim words left off, lists ties instead of picking one, fills only what is missing, and leaves each difference to the owner's one tap."
date: 2026-10-24
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-24
supersedes: []
superseded_by: []
related: [docs/operations/linking-vehicles.md, docs/operations/using-the-catalog-screens.md, docs/reference/vehicle-classification.md, data/vehicle-names.yaml, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0074-nameplates-aliases-and-majority.md, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/decisions/0078-imported-motorcycle-jobs-get-their-class.md, docs/decisions/0079-approval-list.md]
---

# 0077: Customers' vehicles are linked to the catalog by name without guessing, and a class changes only on the owner's tap

**Status:** accepted · **Date:** 2026-10-24 · **Area:** vehicles

## Context

The imported vehicles (Phase 1) carry a year, make and model as typed in Baserow, such as "Chevy" and "Silverado 1500 LT", and a vehicle class chosen by hand. None was linked to a catalog model, so the booking lookup, the history on a model's screen and the approval list (decision 0079) could not reach them. Customers spell makes and models in more ways than the sources do, and often add a trim. A wrong link would price a vehicle with another model's class, and a class picked by hand for a lifted or modified vehicle may be right where the catalog is not. Past jobs keep the price quoted (decision 0059).

## Decision

1. **Names come from data.** `link_vehicles` matches by the names in `data/vehicle-names.yaml`: make spellings such as Chevy and Mercedes, the other spellings of a model, and a new list of trim words. A spelling is added there, never in code.
2. **The longest start of the model field wins,** among catalog models of the make sold in the vehicle's year, and only when every word after it is a trim word. A word a nameplate of that model uses is never dropped, even if it is on the list, so "Wagoneer S" is never matched to the Wagoneer, and a series number such as 2500 is not a trim word.
3. **Never guess.** When two catalog models fit equally, such as a car and a motorcycle of one name, or two owner records covering the year, both are listed and the vehicle stays unlinked. A vehicle no model fits is listed with the nearest name and why it did not fit. The booking lookup's preference for a car over a motorcycle of the same name is not used here.
4. **Linking fills, never changes.** A link sets the vehicle's catalog model and fills a missing class, or a missing size the catalog fixes. It never changes a class or size the vehicle has, and a vehicle linked before keeps its link.
5. **Each difference waits for one tap** on the control app's differences screen: keep the imported class as the vehicle's own override, take the catalog's class, or give every vehicle of the model this vehicle's class with a model override for the years the catalog classes alike. Each is logged with who made it.
6. **The report names vehicles by id, year, make, model and color only,** never by customer, so it can be pasted into a pull request or a chat.

## Alternatives considered

- **Use the booking lookup (`find_model`) as it is.** It picks the first of two candidates, which a booking form can live with but a one-time link of the job history should not.
- **Strip any words after a known model name.** "Silverado 2500" would become a light-duty Silverado and "Santa Fe Sport" a Santa Fe, each in the wrong class or size.
- **Overwrite the imported class with the catalog's.** Would lose the owner's hand-picked class for modified vehicles without anyone looking.

## Consequences

The first dry run lists the spellings to add; the owner reruns until "not found" holds only vehicles that are truly missing. A Baserow import rerun puts each vehicle's imported class back but keeps its link, so `link_vehicles` is run again after it. The per-model choice covers the catalog's year range around the vehicle, not every year of the model, so another generation is not changed by one vehicle; the catalog screen sets any other range.
