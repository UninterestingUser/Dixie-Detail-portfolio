---
title: Classifying the vehicle catalog
summary: How to run classify_vehicles on the server to apply the classification rules and overrides to the vehicle catalog, read its preview and review queue, change a rule or override, and add the Motorcycle Detail price.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-22
tags: [operations, vehicles, classification, phase-2]
related: [docs/reference/vehicle-classification.md, docs/decisions/0073-classification-per-model-year.md, docs/decisions/0072-motorcycles-class.md, docs/operations/importing-vehicle-data.md, data/vehicle-classes.yaml, data/third-row-seating.yaml, docs/guides/editing-the-pricebook.md]
---

# Classifying the vehicle catalog

The `classify_vehicles` command applies the classification rules and overrides to every model year in the vehicle catalog and saves each one's vehicle class and size variant, which the booking lookup reads ([../reference/vehicle-classification.md](../reference/vehicle-classification.md)). It runs in a one-off app container and takes a few seconds.

```text
python manage.py classify_vehicles [--dry-run]
```

Each run first loads the third-row list, [data/third-row-seating.yaml](../../data/third-row-seating.yaml). The first run also seeds the launch rules and model overrides from [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml); later runs leave the rules and overrides in the database as they are. `--dry-run` does all of it inside a transaction that is rolled back, and prints the preview.

It never changes a model override, a customer's vehicle, or anything with source "owner".

## Before the first run

1. The deploy that includes classification has been made; the app applies the new migration when it starts.
2. The catalog is loaded ([importing-vehicle-data.md](importing-vehicle-data.md)). Reload the Canadian specifications once, from the cache, so pickups get their cab styles:

   ```bash
   cd /srv/dixie-detail
   sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
     python manage.py import_vehicle_data --source canada
   ```

3. Load the new vehicle class and service, as in [Adding Motorcycle Detail to the price list](#adding-motorcycle-detail-to-the-price-list) below. `classify_vehicles` needs the Motorcycles class to seed its rule.

## Step 1: Dry run

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py classify_vehicles --dry-run
```

## Step 2: Read the report

- **Launch set seeded** (first run only): how many rules and model overrides, and any override whose model is not in the catalog.
- **Third-row seating list:** model years added, changed, unchanged and removed, and the rows not matched to the catalog, each with the reason. These are left for the owner, not guessed.
- **Model years:** how many are classified by a rule, by a model override, and wait in the review queue, and how many ask the customer the size.
- **Would change:** every model year whose class or size would change, or that would enter or leave the review queue, joined into year ranges, with the old and new values and the rule or override responsible. On the first run that is every model year.
- **Waiting in the review queue:** each model year no rule settles, with the reason: no rule matches, its trims straddle a rule's condition, or its sources disagree.

## Step 3: Apply

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py classify_vehicles
```

The report starts with "APPLIED". Run it again whenever the catalog is reloaded or a rule or override changes.

## Changing a rule or an override

Rules and overrides are edited in the Django admin (`/admin/`, signed in as a superuser) under "Classification rules" and "Model overrides". A rule's conditions are JSON, such as `{"epa_size_class": ["Standard Sport Utility Vehicle 4WD"], "length": {"over": 215}}`; the facts and their forms are in [../reference/vehicle-classification.md](../reference/vehicle-classification.md#facts-a-rule-can-use), and the admin refuses a condition it does not know. Saving changes nothing the customer sees. Run `classify_vehicles --dry-run` to see what the change would do, then run it without `--dry-run` to apply it. To take a model year out of the review queue, add a model override for its model, with a year range if only some years need it.

A customer's lifted or modified vehicle gets its own class on the vehicle's record: its vehicle class and size variant, with the override date, who set it and a note.

## Adding Motorcycle Detail to the price list

Decision 0072 adds the Motorcycles class and the Motorcycle Detail service at $100. On the server pricebook version 1 is already published, so they are added like this:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py load_pricebook
```

It adds the Motorcycles class and the Motorcycle Detail service, fills in each class's photo card caption, and puts the new $100 price in a new draft. It changes no published price. Then publish the draft from the control app's pricebook page with an effective date, as in [../guides/editing-the-pricebook.md](../guides/editing-the-pricebook.md). If a draft is already open, the command refuses and changes nothing; publish or discard that draft, then run it again.
