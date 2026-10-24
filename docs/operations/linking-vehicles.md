---
title: Linking customers' vehicles to the catalog
summary: How to run link_vehicles on the server to link each customer's vehicle to its catalog model, read its report, add spellings, and settle what it finds on the differences screen and the approval list.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-24
tags: [operations, vehicles, classification, phase-2]
related: [docs/decisions/0080-link-vehicles-follow-up.md, docs/decisions/0077-linking-vehicles-to-the-catalog.md, docs/decisions/0078-imported-motorcycle-jobs-get-their-class.md, docs/decisions/0079-approval-list.md, docs/operations/using-the-catalog-screens.md, docs/operations/classifying-vehicles.md, docs/reference/vehicle-classification.md, data/vehicle-names.yaml, data/approval-spot-checks.yaml]
---

# Linking customers' vehicles to the catalog

The `link_vehicles` command links each customer's vehicle to its model in the vehicle catalog, by year, make and model ([decision 0077](../decisions/0077-linking-vehicles-to-the-catalog.md)). It runs in a one-off app container and takes a few seconds.

```text
python manage.py link_vehicles [--dry-run]
```

What it does, and what it never does:

- **It links** a vehicle to the one catalog model of its make, sold in its year, whose name is the longest start of the vehicle's model field, when every word after that name is a trim word. Make spellings, other spellings, customer aliases and trim words come from [data/vehicle-names.yaml](../../data/vehicle-names.yaml), and case and spacing never matter ("Rav4", "Expedition Max").
- **A vehicle with no year** is linked by its make and model when the name fits exactly one catalog model. It keeps its class and size variant, its year stays flagged to fill in at the next visit, and it is not compared on the differences screen, because the class depends on the year ([decision 0080](../decisions/0080-link-vehicles-follow-up.md)).
- **It fills** a missing vehicle class from the catalog, and a missing size variant the catalog fixes, such as two rows from the third-row list. Nothing is filled while the model year waits in the review queue.
- **It never changes** a class or size variant the vehicle has. Each difference waits on the control app's differences screen.
- **It never guesses.** Two catalog models that fit equally are both listed and the vehicle stays unlinked.
- **It keeps** a link made before, and lists the vehicle if it now matches another model.
- **Motorcycles by make:** a vehicle of a make that sells only motorcycles, marked `motorcycles_only` in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml) (Harley-Davidson, Indian, Ducati and others, not Honda, Suzuki or BMW), gets the Motorcycles class when it has none, even with no model or year.
- **Past jobs keep their lines and prices,** except the imported motorcycle jobs, which get the Motorcycles class and the Motorcycle Detail service with their amounts and payments as imported ([decision 0078](../decisions/0078-imported-motorcycle-jobs-get-their-class.md)).

## Before the first run

1. The deploy that includes `link_vehicles` has been made; the app applies the new migration when it starts.
2. The catalog is loaded and classified ([importing-vehicle-data.md](importing-vehicle-data.md), [classifying-vehicles.md](classifying-vehicles.md)), and the Motorcycles class and Motorcycle Detail service are loaded.

## Step 1: Dry run

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py link_vehicles --dry-run
```

## Step 2: Read the report

The report names each vehicle by its id, year, make, model and color, such as "vehicle 41: 2019 Honda Accord, silver", never by customer, so it can be shared.

- **Linked:** each vehicle with the catalog model it links to, the trim words left off ("trim words left off: LE"), and what it fills ("fills size variant two rows"). A vehicle linked by an earlier run says so.
- **Linked, year unknown:** each vehicle with no year linked by make and model, with the class it keeps.
- **Not found:** each vehicle no catalog model fits, with why: no make or model recorded; no year, and the name fits several catalog models, or an alias that holds only for some years; a make the catalog does not have; the catalog has the model but not in that year; or the nearest name and the words after it that are not trim words ("nearest is the Chevrolet Silverado, but '2500HD' is not a trim word").
- **More than one candidate:** each vehicle two catalog models fit equally, with both, such as a car and a motorcycle of one name.
- **Linked before to another model:** a link kept that no longer matches, for you to check.
- **Class or size variant differs from the catalog:** each vehicle whose own class or size differs, with both.
- **Linked, but the catalog has no settled class for the year:** the model year is not classified yet, or waits in the review queue.
- **Imported motorcycle jobs:** each with its date and amount. "CHECK: the amount is not $100.00" marks one whose amount differs from the Motorcycle Detail price, for you to decide; the amount is not changed.
- **Given the Motorcycles class with no catalog year to go by:** each vehicle of a motorcycle-only make, or of a motorcycle model with no year, given the class.
- **Not linked and with no vehicle class:** a motorcycle the names did not find would be here.
- **Name check for unlinked vehicles:** for each unlinked vehicle with a make and model, whether the name would match once a year is known: "the name matches Toyota RAV4 (...)", "the name matches 2 catalog models, which the year tells apart", or "the name matches nothing" with why. A spelling problem shows here even when the year is missing or wrong.

## Step 3: Add spellings, then dry-run again

For a vehicle not found because of a spelling, edit [data/vehicle-names.yaml](../../data/vehicle-names.yaml), never the code:

- A make spelling such as "Chevy" goes under `make_aliases`.
- A model spelling such as "Silverado 1500" goes under `aliases`, with the catalog's name as `name`.
- A customer's name for a vehicle the catalog files under another name or make, such as "Chevrolet 2500" for the Silverado HD or "Dodge Ram" for the Ram 1500, goes under `customer_aliases`, with `from` and `to` when it holds only for some model years (Ram became its own make for 2011). Only `link_vehicles` reads these, so the import never merges catalog models because of them.
- A trim word such as "XLE" goes under `trim_words`. Leave off any word that could name a different vehicle, such as "Sport", "XL" or a series number like 2500.

Merge the change, deploy it, and run the dry run again. A vehicle that is truly missing from the catalog, or has no year, stays unlinked; fix its year, make or model on the customer's vehicle screen if it was typed wrong.

## Step 4: Apply

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py link_vehicles
```

The report starts with "APPLIED". Each vehicle's history records the change as "link_vehicles", and the run is logged with the catalog's other changes. Running it again links only what is new and leaves the rest alone.

## Step 5: Settle the differences and approve the models

In the control app's **Catalog** tab ([using-the-catalog-screens.md](using-the-catalog-screens.md)):

1. **Differences:** for each vehicle, keep the imported class, take the catalog's, or give every vehicle of the model this vehicle's class.
2. **Approvals:** approve or change each year range of every model in the job history, the spot-check list in [data/approval-spot-checks.yaml](../../data/approval-spot-checks.yaml) and every model whose years are in different classes ([decision 0079](../decisions/0079-approval-list.md)). Phase 2 is done when every model there is approved.

## After a Baserow import rerun

A rerun of `import_baserow` puts each vehicle's imported class back, and recreates the motorcycle jobs as custom lines, but keeps each vehicle's link. Run `link_vehicles` again afterwards, then check the differences screen.
