---
title: Importing the Baserow and Setmore records
summary: How to copy the Baserow and Setmore exports and the corrections file to the server, dry-run the import, apply it, re-run it with fresh exports, and remove the files afterwards.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-18
tags: [operations, import, baserow, setmore, migration]
related: [docs/reference/data-migration.md, docs/decisions/0036-baserow-import.md, docs/decisions/0051-baserow-ids-kept-on-import.md, docs/decisions/0066-imported-payments-already-in-the-books.md, data/configuration.yaml]
---

# Importing the Baserow and Setmore records

The `import_baserow` command reads a folder of export files and imports customers, vehicles, appointments, payments and staff into the database, following [../reference/data-migration.md](../reference/data-migration.md). It runs in a one-off app container with the folder mounted read-only. Without `--apply` it is a dry run that changes nothing. The import can be run as often as needed before launch; each run updates what the last one wrote (decision 0051).

The export files and the corrections file hold customers' personal data. They never go in the repository, an issue or a pull request, and they are removed from the server after each run.

## What the folder holds

On the workstation the exports live in a dated folder such as `"$HOME/Dixie Detail/imports/2026-10-17"`. The folder needs these files, found by name:

| File | Found by |
| --- | --- |
| Baserow Customers, Vehicles, Appointments and Bookkeeping exports | The table name as a word in the file name, so `export - Customers.csv` and `BaserowExport - Customers - Grid.csv` both work. Exactly one file per table |
| The Setmore contact list | A CSV with "Setmore" in its name, such as `SetmoreContacts.csv` |
| `import-corrections.yaml` | That exact name. Its own `meta` and `rules` sections describe it |

Export all four Baserow tables on the same day, so the links between them agree.

## Before the first run

1. The deploy that includes the importer has been made, and the stack is running.
2. The pricebook is loaded (`load_pricebook`, in [deploying-changes.md](deploying-changes.md)). The import needs its vehicle classes and services and stops if they are missing.

## Step 1: Copy the folder to the server

From the workstation, over the tailnet:

```bash
ssh grassman-server rm -rf dixie-import
scp -r "$HOME/Dixie Detail/imports/2026-10-17" grassman-server:dixie-import
```

Then on the server, move it to the import folder and make it readable only by the app container's user (uid 10001):

```bash
sudo rm -rf /srv/dixie-import
sudo mv ~/dixie-import /srv/dixie-import
sudo chown -R 10001:10001 /srv/dixie-import
sudo chmod -R u=rX,go= /srv/dixie-import
```

The host folder `/srv/dixie-import` and the container folder `/srv/import` are recorded in [data/configuration.yaml](../../data/configuration.yaml).

## Step 2: Dry run

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-import:/srv/import:ro app \
  python manage.py import_baserow --owner "OWNER NAME AS IN BASEROW"
```

`--owner` names the owner as written in the Appointments table's Staff column. It is needed until the staff records exist: each other name in that column is created as a family helper. Without it, the staff are listed under "Could not place". The owner is never a helper, so a Wage Override on a job with the owner and one helper is that helper's pay.

The dry run imports everything inside a transaction and then rolls it back, so its report shows exactly what `--apply` would write. Read every section:

- **Counts** of each kind of record, created or updated.
- **Corrections applied:** every entry in the corrections file that was used, with its reason.
- **Warnings:** things imported with a gap, such as a vehicle left blank because a customer has two vehicles of the same name, or a name in the corrections file that no longer matches the export.
- **Could not place:** every row left out, and why, such as a link to a customer who is not in the export.
- **Helper pay:** every helper's pay for a job, with the amount, the date, whether it was paid and where the amount came from (the Wage Override or the corrections file). Check each against GnuCash's Professional Services entries.
- **Questions in the corrections file,** left alone until the owner settles them.
- **Expected results from the corrections file,** to compare with the counts.

Fix a problem in Baserow or in the corrections file, export again, copy again and repeat the dry run until the report is right. For a warning that a customer has two vehicles of the same name, add the job to `appointment_fixes` with `set: {vehicle_baserow_id: N}`, where N is the right vehicle's id in the Vehicles export; the next report shows "linked to vehicle N" under "Corrections applied". For a warning about a Wage Override with two helpers, add the job to `appointment_fixes` with `helper_pay: {Name: amount}` for each helper, named as in the Staff column.

## Step 3: Apply

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-import:/srv/import:ro app \
  python manage.py import_baserow --owner "OWNER NAME AS IN BASEROW" --apply
```

The report is the same, headed "APPLIED". Then spot-check a few customers, every booked job's time and price, and a few completed jobs in the control app.

## Step 4: Remove the files

```bash
sudo rm -rf /srv/dixie-import
```

The workstation copy stays in the private folder until Baserow is retired.

## Running it again with fresh exports

Repeat steps 1 to 4 with the new folder. Records are found by their Baserow ids, so a re-run updates customers, vehicles, appointments, their lines, payments and assignments instead of duplicating them, and removes imported payments the new exports no longer give. `--owner` can be left out once the staff exist.

Until the last run before launch, fix imported records in Baserow or the corrections file, not in the app: a re-run overwrites imported fields with the export's values. After the last run, Baserow is retired.

## What the import assumes

- Baserow times are UTC; they are stored so they show in Eastern.
- A job's Hours is its whole time on site. Setup and breakdown are split from it by the crew size, and the rest is service time. Most past jobs have no Hours and keep no times.
- Imported payments and helper payouts are already in GnuCash, so they are held by the export batch "Already in GnuCash: Baserow import" and the GnuCash export never sends them (decision 0066).
- Baserow does not record how a helper was paid, so an imported helper payout is entered as cash with a note; change it in the app if it was paid another way.
