---
title: Classifying the vehicle catalog
summary: How to run classify_vehicles to apply the rules and overrides, read its preview and review queue, change a rule or override, and switch to the size-based classes with apply_size_classes.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-29
tags: [operations, vehicles, classification, phase-2]
related: [docs/decisions/0083-applying-the-size-based-classes.md, data/size-classes.yaml, docs/decisions/0081-monthly-vehicle-data-refresh.md, docs/operations/using-the-catalog-screens.md, docs/decisions/0075-unpublished-years-and-canadian-nameplates.md, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/reference/vehicle-classification.md, docs/decisions/0074-nameplates-aliases-and-majority.md, docs/decisions/0073-classification-per-model-year.md, docs/decisions/0072-motorcycles-class.md, docs/operations/importing-vehicle-data.md, data/vehicle-classes.yaml, data/third-row-seating.yaml, docs/guides/editing-the-pricebook.md]
---

# Classifying the vehicle catalog

The `classify_vehicles` command applies the classification rules and overrides to every model year in the vehicle catalog and saves each one's vehicle class and size variant, which the booking lookup reads ([../reference/vehicle-classification.md](../reference/vehicle-classification.md)). It runs in a one-off app container and takes a few seconds.

```text
python manage.py classify_vehicles [--dry-run] [--refresh]
```

Each run first brings the launch rules and model overrides in step with [data/size-classes.yaml](../../data/size-classes.yaml): it adds a new entry, updates one you have not edited, and removes one taken out of the file. One you edited or deleted in the database is left alone, and your own rules and overrides are never touched. Then it loads the third-row list, [data/third-row-seating.yaml](../../data/third-row-seating.yaml). `--dry-run` does all of it inside a transaction that is rolled back, and prints the preview. Until `apply_size_classes` has switched the catalog to the size-based classes ([below](#applying-the-size-based-classes)), it leaves the body-type rules already in the database as they are, and says so.

It never changes an override you set or edited, a review queue decision, a customer's vehicle, or anything with source "owner". Each applied run is logged, and shows in each changed model's history in the control app.

`--refresh` runs it as the monthly refresh does ([decision 0081](../decisions/0081-monthly-vehicle-data-refresh.md)): a model year whose class or size would change is held in the review queue instead, keeping its class, when its model has a model override, an approval on the approval list or customers' jobs. The report then lists the held model years, with the old and new values. Without `--refresh`, the command applies every change, as you see it in the dry run. The monthly refresh runs this for you after reloading the data ([monitoring.md](monitoring.md)).

Day to day, rules, overrides, class settings and the review queue are changed in the control app's **Catalog** tab, which applies each change itself ([using-the-catalog-screens.md](using-the-catalog-screens.md)). Run this command after the catalog is reloaded, or when the data files change. A run that alters a year range you approved on the approval list clears that approval. Customers' vehicles are linked to the catalog by a separate command ([linking-vehicles.md](linking-vehicles.md)).

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
- **Model years:** how many are classified by a rule, by a model override, by a review queue decision, from the nearest classified year (a year the EPA has not published yet), by the pickup size line, as a pickup in other model years, by the three-row floor, by the EPA size class fallback, by smoothing, sent to the photo cards, and wait in the review queue, and how many ask the customer the size.
- **Model years by class and size:** the classified model years in each vehicle class, and within it by size variant or "ask".
- **Would change:** every model year whose class or size would change, or that would enter or leave the review queue, joined into year ranges, with the old and new values and the rule or override responsible. On the first run that is every model year.
- **Smoothed:** every run of up to six model years given the class of the runs on either side, such as "Acme Roamer 2019-2020: Medium, smoothed from Large", then those smoothed away from the class of the model's newest generation.
- **Models whose years are in different classes:** each model with its year ranges and their classes, such as "Toyota Highlander: 2013: Medium; 2014-2026: Large", for you to look at.
- **Waiting in the review queue:** each model year no rule settles, with the reason: no rule matches, its rows have no clear majority on a rule's condition (the split is shown, such as "3 of 6 rows (50%) meet it"), or its sources disagree.

## Step 3: Apply

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py classify_vehicles
```

The report starts with "APPLIED". Run it again whenever the catalog is reloaded or a rule or override changes.

## Changing a rule or an override

Use the control app's **Catalog** tab ([using-the-catalog-screens.md](using-the-catalog-screens.md)): a rule change shows its preview and applies when you confirm it; an override, the third-row flag and a review queue decision apply at once. A customer's lifted or modified vehicle gets its own class on the vehicle's edit screen.

The Django admin (`/admin/`, signed in as a superuser) still lists "Classification rules", "Model overrides" and "Review decisions" for fixing data by hand. A rule's conditions there are JSON, such as `{"box_volume": {"at_least": 580, "under": 700}}`; the facts and their forms are in [../reference/vehicle-classification.md](../reference/vehicle-classification.md#facts-a-rule-can-use), and the admin refuses a condition it does not know. A change saved in the admin changes nothing the customer sees until this command applies it.

## Adding Motorcycle Detail to the price list

Decision 0072 adds the Motorcycles class and the Motorcycle Detail service at $100. On the server pricebook version 1 is already published, so they are added like this:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py load_pricebook
```

It adds the Motorcycles class and the Motorcycle Detail service, fills in each class's photo card caption, and puts the new $100 price in a new draft. It changes no published price. Then publish the draft from the control app's pricebook page with an effective date, as in [../guides/editing-the-pricebook.md](../guides/editing-the-pricebook.md). If a draft is already open, the command refuses and changes nothing; publish or discard that draft, then run it again.

## Applying the size-based classes

The size-based classes ([decisions 0082](../decisions/0082-size-based-vehicle-classes.md) and [0083](../decisions/0083-applying-the-size-based-classes.md)) and the new price book in [data/price-matrix.csv](../../data/price-matrix.csv) go live together, in one step, with `apply_size_classes`. The owner applied them on 2026-10-28; the steps below are kept for a rebuilt server and as the record of how it is done, and a second run says the classes are already applied. It runs in one transaction, so the classes and the prices never disagree, and a dry run does everything, prints the same report and rolls back. The classes, lines and rules are in [../reference/vehicle-classification.md](../reference/vehicle-classification.md).

```text
python manage.py apply_size_classes --effective YYYY-MM-DD [--dry-run]
```

### Step 1: Load the new price book as a draft

After the deploy that includes it:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py load_pricebook
```

`load_pricebook` first runs the price book check on the file ([../reference/pricing.md](../reference/pricing.md#the-price-book-check)) and changes nothing if it fails. Then it creates Small, Medium, Large, Full-size and Full-size Vans as pending classes, which booking, quoting and the catalog screens do not offer yet, and loads the whole matrix as a new draft version. Light Pickups and Full-size Trucks are priced under their old names, Light Pickups & Offroad and Fullsize Trucks, until the switch renames them. The draft cannot be published from the control app: it waits for `apply_size_classes`. If another draft is open, publish or discard it first.

### Step 2: Dry run

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py apply_size_classes --effective YYYY-MM-DD --dry-run > size-classes-dry-run.txt
```

Give the day you will apply it. The report holds vehicle ids, years, makes and models, and booked jobs by appointment id and date, but no customer names. Copy it off the server and delete it there once you have it. It starts with "DRY RUN", or "REFUSED" when the draft fails the price book check, and then lists:

- **The switch:** the classes renamed, offered and retired; how many rules, model overrides, review queue decisions and approvals are archived; the launch rules and overrides created from data/size-classes.yaml, and any override whose model is not in the catalog; and the classification counts.
- **Price book check:** passed, or each problem, such as a class and row count the catalog gives with no Full Detail price, with the model years that give it. A failed check refuses the switch; add the price, or the size variant, and load the price book again. Full-size and minivans are always three rows and one row exists only in Small, so the check counts only those rows.
- **Model years by new class and source of the class:** for each class, how many model years have their own measurements, inherited a box volume, need none (pickups and motorcycles), took the EPA size class fallback, have a model override, or were smoothed; then how many wait in the review queue.
- **EPA size class fallback:** for each EPA size class, the class most of its measured model years land in, with the counts behind it.
- **Near a line:** every model within 5 cubic feet of a size line or the pickup line (its newest size range from 2015 on, plus any range a customer owns), with its box volume and customer vehicles.
- **Smoothed:** every run of model years given the class around it, then, on their own, the smoothed runs whose new class is not the class of the model's newest generation: a backwards smooth, worth a look ([decision 0085](../decisions/0085-size-class-fixes-after-the-first-dry-run.md)).
- **Models whose class changes between model years,** as year ranges.
- **Model overrides now,** the three from data/size-classes.yaml, then the **archived model overrides, review queue decisions and approvals,** each with what the new rules give instead.
- **Customer vehicles:** counts by recorded and new class, how many had no year and took their model's newest generation (flagged to confirm the year at the next visit), how many stay in a retired class for the differences screen, then each vehicle one by one.
- **Booked jobs to check by hand:** each booked job in a retired class that has no vehicle, or whose vehicle has no class or size variant (no year, or unclassified), by appointment id, date and vehicle. These are not re-priced and keep their quoted price; give the vehicle its class and size, then decide the job on the booked-job review ([decision 0084](../decisions/0084-booked-jobs-with-no-vehicle-or-class.md)).
- **Booked jobs:** each other booked job from the effective date on that the new price book prices differently, with its quoted price, its price in the vehicle's new class, and why. Each keeps its quoted price.
- **Models now in Light Pickups & Offroad that the new rules do not treat as pickups,** such as the Jeep Wrangler.
- **Pickup ladder:** every pickup model's newest size range, sorted by box volume, with the 760 cubic foot line marked, its length, cab styles, EPA size class, GVWR range and class before and after, then the largest steps.
- **Pickup check and van check:** whether the Santa Cruz and Maverick are pickups in every model year, and every van model with its classes, flagged if it is a pickup in any year.

### Step 3: Apply on the effective date

On the effective date, run it without `--dry-run`:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py apply_size_classes --effective YYYY-MM-DD
```

If it stops partway, for a reason the checks do not foresee, its error names the step it was on and the appointment or vehicle it was working on, and nothing is changed. It refuses any date but today, because the classes switch when it runs and the prices must take effect the same day. The report starts with "APPLIED". It publishes the draft, renames Light Pickups & Offroad and Fullsize Trucks, offers the new classes, retires Coupes & Sedans, Crossovers & Wagons, Midsize SUVs and Fullsize SUVs & Minivans, archives the old rules, overrides, decisions and approvals, classifies every model year, and sets each customer's vehicle's class. Past jobs keep their classes and prices. Run it once; a second run says the classes are already applied.

### Step 4: Settle what waits for you

1. **Booked jobs:** the published version's page in the control app says how many booked jobs wait for your choice. On its booked-job review, keep each job's quoted price, use the new price, or give a custom amount ([using-the-catalog-screens.md](using-the-catalog-screens.md)).
2. **Vehicles left in a retired class:** the **Differences** screen lists each under "Left in a retired class" with a proposed class; save it or pick another.
3. **The approval list** has started over: approve each model on the **Approvals** screen.
4. **Photo cards:** each class's card shows a placeholder until you add its photo on the class settings screen.

## Vehicle size report

The vehicle size report gathered the facts for decision 0082 from the body-type classes. Since the switch those classes are retired, so it finds only the review queue's model years; the `apply_size_classes` and `classify_vehicles` reports replace it.

The `vehicle_size_report` command prints the measured size of every model in the car, crossover and SUV classes, as facts for deciding whether to split those classes differently. It only reads facts already in the database: it makes no network calls, runs in a read-only transaction and changes no class, rule, override, approval, price or vehicle.

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps app python manage.py vehicle_size_report --format summary
sudo docker compose run --rm --no-deps app python manage.py vehicle_size_report --format csv > vehicle-sizes.csv
```

**What the vehicle size report covers:** the model years now in Coupes & Sedans, Crossovers & Wagons and Midsize SUVs, Fullsize SUVs & Minivans for comparison, and the model years waiting in the review queue with no class whose EPA size class is a car, station-wagon or SUV class, shown as "in queue".

**How the vehicle size report groups model years:** one row per model and size range. A model's consecutive model years share a row while they keep the same class and seat rows and their length, width and height each stay within 1 inch. Where trims differ, each model year's figure is the median of its trims, read the way classification reads it (the owner's own figures first, then the Canadian specifications), and the row's figure is the median of its years'. Box volume is length × width × height ÷ 1,728, in cubic feet: a rough measure of bulk, not cargo space.

**The CSV (`--format csv`)** has every row, with units in the headers: make, catalog model name, years, current class or "in queue", seat rows (2, 3 or optional, from the third-row data), doors for cars, EPA size classes, length, width, height and wheelbase in inches, curb weight in pounds, box volume, the number of trims with specs and their shortest and longest length, and the counts of customer vehicles and completed jobs in those years, plus the model's customer vehicles with no year. Rows with no length, width or height are marked "missing".

**The summary (`--format summary`, the default)** has five parts:

- **Crossovers and SUVs:** a 2-row ladder sorted by box volume, one line per model for its newest size range from 2015 on, plus any older range a customer owns; a 3-row ladder (an optional third row included); and Fullsize SUVs & Minivans last for comparison. Each line shows box volume, length and current class, and `*` marks lines with customer vehicles.
- **Candidate lines:** the five largest steps in box volume and the five largest in length along the 2-row ladder, with the models on each side.
- **Cars and wagons:** the same ladder for Coupes & Sedans and for the wagons in Crossovers & Wagons (EPA station-wagon classes), with each model's main EPA size class, and the number of models and customer vehicles in each EPA car class.
- **Customer vehicles by their recorded class:** linked with a year, linked with no year, and unlinked.
- **Data gaps:** models in scope with no dimensions, and how many customer vehicles they hold.

Customers appear only as counts: the vehicle size report never prints a name, phone number or address. Copy a CSV off the server and delete it there once you have it.
