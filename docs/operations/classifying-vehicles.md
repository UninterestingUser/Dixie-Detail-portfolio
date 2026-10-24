---
title: Classifying the vehicle catalog
summary: How to run classify_vehicles on the server to apply the classification rules and overrides to the vehicle catalog, read its preview and review queue, change a rule or override, and add the Motorcycle Detail price.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-23
tags: [operations, vehicles, classification, phase-2]
related: [docs/operations/using-the-catalog-screens.md, docs/decisions/0075-unpublished-years-and-canadian-nameplates.md, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/reference/vehicle-classification.md, docs/decisions/0074-nameplates-aliases-and-majority.md, docs/decisions/0073-classification-per-model-year.md, docs/decisions/0072-motorcycles-class.md, docs/operations/importing-vehicle-data.md, data/vehicle-classes.yaml, data/third-row-seating.yaml, docs/guides/editing-the-pricebook.md]
---

# Classifying the vehicle catalog

The `classify_vehicles` command applies the classification rules and overrides to every model year in the vehicle catalog and saves each one's vehicle class and size variant, which the booking lookup reads ([../reference/vehicle-classification.md](../reference/vehicle-classification.md)). It runs in a one-off app container and takes a few seconds.

```text
python manage.py classify_vehicles [--dry-run]
```

Each run first brings the launch rules and model overrides in step with [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml): it adds a new entry, updates one you have not edited, and removes one taken out of the file. One you edited or deleted in the database is left alone, and your own rules and overrides are never touched. Then it loads the third-row list, [data/third-row-seating.yaml](../../data/third-row-seating.yaml). `--dry-run` does all of it inside a transaction that is rolled back, and prints the preview.

It never changes an override you set or edited, a review queue decision, a customer's vehicle, or anything with source "owner". Each applied run is logged, and shows in each changed model's history in the control app.

Day to day, rules, overrides, class settings and the review queue are changed in the control app's **Catalog** tab, which applies each change itself ([using-the-catalog-screens.md](using-the-catalog-screens.md)). Run this command after the catalog is reloaded, or when the data files change.

## Before the first run

1. The deploy that includes classification has been made; the app applies the new migration when it starts.
2. The catalog is loaded ([importing-vehicle-data.md](importing-vehicle-data.md)). Reload the Canadian specifications once, from the cache, so pickups get their cab styles:

   ```bash
   cd /srv/dixie-detail
   sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
     python manage.py import_vehicle_data --source canada
   ```

   Run it again once after the deploy that splits Canadian trims by nameplate ([decision 0075](../decisions/0075-unpublished-years-and-canadian-nameplates.md)), so the EQE and EQS SUVs get their own weights instead of the sedans'.

3. Load the new vehicle class and service, as in [Adding Motorcycle Detail to the price list](#adding-motorcycle-detail-to-the-price-list) below. `classify_vehicles` needs the Motorcycles class to seed its rule.

## Step 1: Dry run

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py classify_vehicles --dry-run
```

## Step 2: Read the report

- **Launch rules and overrides:** each rule or override added, updated or removed to follow the file, each one kept because you edited or deleted it, and any override whose model is not in the catalog.
- **Third-row seating list:** model years added, changed, unchanged and removed, and the rows not matched to the catalog, each with the reason. These are left for the owner, not guessed.
- **Model years:** how many are classified by a rule, by a model override, by a review queue decision, from the nearest classified year (a year the EPA has not published yet), sent to the photo cards, and wait in the review queue, and how many ask the customer the size.
- **Model years by class and size:** the classified model years in each vehicle class, and within it by size variant or "ask".
- **Would change:** every model year whose class or size would change, or that would enter or leave the review queue, joined into year ranges, with the old and new values and the rule or override responsible. On the first run that is every model year.
- **Models whose years are in different classes:** each model with its year ranges and their classes, such as "Toyota Highlander: 2013: Crossovers & Wagons; 2014-2026: Midsize SUVs", for you to look at when the job history is checked (Phase 2 Step 4).
- **Waiting in the review queue:** each model year no rule settles, with the reason: no rule matches, its rows have no clear majority on a rule's condition (the split is shown, such as "3 of 6 rows (50%) meet it"), or its sources disagree.

## Step 3: Apply

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py classify_vehicles
```

The report starts with "APPLIED". Run it again whenever the catalog is reloaded or a rule or override changes.

## Changing a rule or an override

Use the control app's **Catalog** tab ([using-the-catalog-screens.md](using-the-catalog-screens.md)): a rule change shows its preview and applies when you confirm it; an override, the third-row flag and a review queue decision apply at once. A customer's lifted or modified vehicle gets its own class on the vehicle's edit screen.

The Django admin (`/admin/`, signed in as a superuser) still lists "Classification rules", "Model overrides" and "Review decisions" for fixing data by hand. A rule's conditions there are JSON, such as `{"epa_size_class": ["Standard Sport Utility Vehicle 4WD"], "length": {"over": 215}}`; the facts and their forms are in [../reference/vehicle-classification.md](../reference/vehicle-classification.md#facts-a-rule-can-use), and the admin refuses a condition it does not know. A change saved in the admin changes nothing the customer sees until this command applies it.

## Adding Motorcycle Detail to the price list

Decision 0072 adds the Motorcycles class and the Motorcycle Detail service at $100. On the server pricebook version 1 is already published, so they are added like this:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py load_pricebook
```

It adds the Motorcycles class and the Motorcycle Detail service, fills in each class's photo card caption, and puts the new $100 price in a new draft. It changes no published price. Then publish the draft from the control app's pricebook page with an effective date, as in [../guides/editing-the-pricebook.md](../guides/editing-the-pricebook.md). If a draft is already open, the command refuses and changes nothing; publish or discard that draft, then run it again.
