---
title: Importing the vehicle data
summary: How to run import_vehicle_data on the server to load the vehicle catalog from the EPA, NHTSA vPIC and the Canadian specifications, read its report, rerun it, and add a make.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-22
tags: [operations, import, vehicles, epa, vpic, phase-2]
related: [docs/reference/vehicle-catalog.md, docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, data/vehicle-data-import.yaml, data/integrations.yaml, data/configuration.yaml, docs/operations/troubleshooting.md]
---

# Importing the vehicle data

The `import_vehicle_data` command loads the vehicle catalog ([../reference/vehicle-catalog.md](../reference/vehicle-catalog.md)) from three free sources, in this order: the EPA's FuelEconomy.gov table, NHTSA vPIC's model lists, and vPIC's Canadian specifications. It runs in a one-off app container. The data is public, so nothing here is personal or secret.

```text
python manage.py import_vehicle_data [--source epa|vpic|canada|all] [--dry-run] [--refresh]
```

- `--source` picks one source; the default is `all`. The Canadian specifications attach to the models already in the catalog, so run them after the other two.
- `--dry-run` imports everything inside a transaction that is then rolled back, so the report shows what a real run would write and nothing changes. A dry run of `all` matches the Canadian rows against the models the same dry run would add.
- `--refresh` downloads every file again instead of using the cache. Use it to pick up new data from the sources; without it a rerun uses the files already downloaded.

## The download cache

Every file the import downloads is kept in the folder named by the setting `VEHICLE_DATA_CACHE_DIR`, `/srv/vehicle-data` in the container by default, so a rerun does not fetch again. On the server that is the host folder `/srv/dixie-vehicle-data`, outside the repository, mounted read-write into the one-off container. Both paths are in [data/configuration.yaml](../../data/configuration.yaml). The cache holds the EPA's zip file and one small JSON file per vPIC call, and can be deleted at any time; the next run downloads again.

Create it once, owned by the app container's user (uid 10001):

```bash
sudo mkdir -p /srv/dixie-vehicle-data
sudo chown 10001:10001 /srv/dixie-vehicle-data
sudo chmod 700 /srv/dixie-vehicle-data
```

## How long a run takes

The EPA's table is one download of about 2 MB. vPIC is asked once per make, model year and vehicle type, and the Canadian specifications once per make and model year in the catalog: about 3,500 calls from 1984 to the next model year. The import waits a second between vPIC calls and retries a "429 Too Many Requests" or a 5xx answer up to four times with a growing wait, so the first full run takes an hour or more. Progress is printed every 100 calls. A rerun from the cache takes under a minute. The pause, retries and wait are in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml).

## Before the first run

1. The deploy that includes the import has been made and the stack is running. The app applies the new database migration when it starts.
2. The cache folder exists, as above.

## Step 1: Dry run

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data --dry-run
```

The dry run downloads into the cache, so the real run after it does not fetch again. Run it inside `tmux` or `screen` the first time, so a dropped SSH session does not stop it.

## Step 2: Read the report

The report has one section per source:

- **Models added, changed and unchanged.** A model is changed when one of its model years from this source was added or changed, or its year range moved.
- **Model years added, changed and unchanged.** A model year is the source's facts about one model in one year.
- **Owner's models: facts recorded, model left alone.** Models with source "owner" that the source also lists. Their name and years are never changed.
- **Files downloaded and from the cache.**
- **Models added** (vPIC only): every pickup, van and motorcycle model vPIC added that the EPA does not have. Some are commercial trucks or an EPA model under another name; the review queue in a later step handles them.
- **Canadian rows not matched to a model, left for the owner.** Each row, with the reason: no catalog model begins the name, two match equally, or the name goes on with a series number such as 2500HD. These are listed, not guessed.
- **Rejected.** Rows that could not be used, with the reason: an EPA row with no model year, a vPIC make not in the list for the make asked for, or a Canadian row with no weight or dimensions.

## Step 3: Apply

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data
```

The report starts with "APPLIED". Each source is written on its own: if vPIC fails, the EPA's work is kept, the command exits with an error naming the source, and a rerun picks up from the cache.

## Every run is recorded

Each run of each source, dry or real, is recorded with its start, end, counts and result, under "Vehicle data import runs" in the Django admin. A failed run records why it stopped.

## Adding a make or a vPIC make name

The makes vPIC is asked for are listed in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml), each with the vPIC make names to accept, because vPIC matches names loosely: asking for "indian" also returns "PERFORMANCE INDIAN". When the report rejects a vPIC make that belongs, such as KTMMEX for KTM, add it to that make's `vpic_names`. When the Canadian specifications spell a make differently from the catalog, as they write "RAM TRUCKS" for Ram, add it under `canada.make_names`. Either change goes in a pull request; the next run picks it up with no code change.

## Rerunning with fresh data

The EPA updates its table as new models are tested, and vPIC adds models through the year. To pick them up:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data --refresh --dry-run
```

Then run it again without `--dry-run`; the files are already fresh in the cache. A rerun changes only what the sources changed, never anything with source "owner", and keeps the model years a source no longer lists, with the date it last listed them.
