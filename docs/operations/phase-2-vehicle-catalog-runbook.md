---
title: Phase 2 vehicle catalog runbook
summary: The runbook that built Phase 2 (vehicle data, classification, catalog screens, linked vehicles, monthly refresh, size-based classes) as run from 2026-10-21 to 2026-10-29, kept as a historical record.
audience: [owner, developer]
visibility: restricted
status: historical
updated: 2026-10-29
tags: [phase-2, runbook, history, vehicles]
related: [docs/overview/roadmap.md, data/phases.yaml, docs/operations/phase-1-core-data-runbook.md, docs/reference/vehicle-classification.md, docs/operations/importing-vehicle-data.md]
---

> Historical record. This runbook was kept as a working document in the Claude app during Phase 2 and copied here when the phase closed on 2026-10-29. The task prompts are as they were given to Claude Code, and later sections correct earlier ones in the order things happened: the body-type classes built in Steps 2 to 4 were replaced on 2026-10-29 by the size-based classes and price book in the side task near the end, and the motorcycle detail time changed from 1 to 2 hours of service. The third-row list the owner checked is data/third-row-seating.yaml. For how things work now, follow the reference and operations docs, not this page.

# Phase 2: Vehicle catalog runbook

Oct 21, 2026 · @Kris Grassman

## What Phase 2 delivers

Phase 2 builds the vehicle catalog: every year, make and model from the EPA and NHTSA data, each with a vehicle class and a size rule, decided by rules you can edit and override. Phase 3's booking form will use it to price a vehicle from year, make and model alone. The design is already settled in docs/reference/vehicle-classification.md and decision 0060; this runbook turns it into steps.

| Step | You | Claude Code, in the repo |
| --- | --- | --- |
| Before you start | Read the decisions at the end of this runbook | One small docs fix left from Phase 1 |
| 1. Vehicle data | Run the first download on the server, read the report | EPA and NHTSA download into the catalog, with each model year's facts |
| 2. Classification rules | Read the launch rules | Rules as data, overrides, size rules, a preview, and the lookup the website will use |
| 3. Catalog screens | Try the screens on the Pixel | Catalog search, rule editing with preview, overrides, class settings, review queue |
| 4. Your vehicles | Approve every model in your job history and a spot-check list | Link your imported vehicles to the catalog, with a report of every difference |
| 5. Monthly refresh | Create one Healthchecks check | A monthly timer that re-downloads, classifies new models and queues anything unclear |
| 6. Acceptance | Run the done test | Mark Phase 2 done, copy this runbook into the repo |

**Done when** (from the roadmap): you approve the vehicle class for every model in your job history and for a spot-check list of tricky models.

The same habits as Phase 1 apply: one Claude Code task per step, `sudo /srv/dixie-detail/ops/deploy.sh` after each merge, US English, and a portfolio publish when the phase closes.

## Before you start

1. **Read the decisions at the end of this runbook.** They are settled and already written into the tasks: no new price factors in v1.0, motorcycles become a class at a flat $100, and I prepare the third-row list. You check that list before Step 2.
2. **Pull the latest main on the workstation** and confirm the server is on it: `sudo /srv/dixie-detail/ops/deploy.sh` reports nothing new to deploy.
3. **No new accounts or secrets.** The EPA and NHTSA data are free and need no key, so nothing goes into Bitwarden until Step 5's Healthchecks check.
4. **One leftover from Phase 1** goes into the Step 1 task: decision 0027 still gives the old backup time, so it gets marked as superseded by decision 0070.

Management commands run inside the app container the same way as in Phase 1, for example `sudo docker exec dixie-app-1 python manage.py <command>`.

## Step 1: Load the EPA and NHTSA data

This step fills the catalog with facts only. Nothing is classified yet, and your customers' vehicles are not touched.

**Claude Code task:**

> Phase 2, Step 1: load the vehicle data. Read docs/reference/vehicle-classification.md, data/vehicle-classes.yaml, data/integrations.yaml and decisions 0029, 0060 and 0064 first.
>
> 1. **Store facts per model year.** `VehicleModel` stays the thing a customer picks and a class applies to. Add what is needed to keep each model year's facts from each source: EPA size class, drive, body styles, passenger and luggage volume, GVWR range, curb weight range, length, width, height and wheelbase, with the source, the source's own IDs, and when the row was first and last seen. EPA lists one row per engine and transmission, so keep the range across a model year's rows rather than one row. Explain the design in the pull request.
> 2. **EPA importer.** Download `vehicles.csv.zip` from FuelEconomy.gov (record the URL in data/integrations.yaml) and load 1984 onward. The EPA has no door field: work out the body styles from which of `pv2`/`lv2` (two-door), `pv4`/`lv4` (four-door) and `hpv`/`hlv` (hatchback) are nonzero, and record "unknown" when all are zero, as they are for pickups, vans and most SUVs.
> 3. **vPIC gap fill.** Add the makes and models the EPA leaves out, chiefly pickups and vans over 8,500 lb GVWR (2500 and 3500 series, Super Duty and similar), using GetModelsForMakeYear for trucks and multipurpose vehicles. **Also load motorcycle models** with GetModelsForMakeYear for vehicle type motorcycle, for the motorcycle makes in a list kept in data (start with Harley-Davidson, Honda, Yamaha, Kawasaki, Suzuki, BMW, Ducati, Triumph, KTM, Indian, Aprilia, Moto Guzzi, Royal Enfield, Husqvarna, Victory and Zero), and mark each one's vehicle type as motorcycle. The booking form will show them in the same year, make and model lists as cars. Keep the list of makes to query in data, not in code.
> 4. **Canadian specifications.** Call GetCanadianVehicleSpecifications by year and make for the makes already in the catalog, and attach curb weight and the four dimensions to matching models. List what did not match in the report instead of guessing.
> 5. **One command:** `python manage.py import_vehicle_data` with `--source epa|vpic|canada|all` and `--dry-run`. It prints a report: models and model years added, changed and unchanged per source, unmatched Canadian rows, and anything rejected. Record each run (start, end, counts, result) in the database for Step 5.
> 6. **Be a polite client.** Cache raw downloads in a folder named by a setting, outside the repository, so a rerun does not fetch again. Pause between vPIC calls and retry 429 and 5xx responses with backoff, as `ops/lib/bws.sh` does.
> 7. **Never overwrite the owner.** Anything with source "owner" is left alone by every import, now and in later steps.
> 8. **Tests** use small fixture files with no network access. Update data/integrations.yaml to "In progress", the classification doc where the design changed, and docs/operations/ with how to run the import.
> 9. **Phase 1 leftover:** mark decision 0027 as superseded by 0070 for the backup time.
>
> Open a pull request.

**You, after merging:**

```bash
sudo /srv/dixie-detail/ops/deploy.sh
sudo mkdir -p /srv/dixie-vehicle-data
sudo chown 10001:10001 /srv/dixie-vehicle-data
sudo chmod 700 /srv/dixie-vehicle-data
tmux new -s vehicles
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data --dry-run
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data
```

The import runs in a one-off container with the download folder attached (`/srv/dixie-vehicle-data` on the server is `/srv/vehicle-data` inside), not with `docker exec`, which has no such folder. The first dry run takes an hour or more because of the pauses between NHTSA calls, so it runs inside `tmux` (after a dropped connection, `tmux attach -t vehicles`); the real run after it uses the downloaded files and takes under a minute. The guide is docs/operations/importing-vehicle-data.md. **Check:** the report shows tens of thousands of EPA model years from 1984 on, vPIC truck, van and motorcycle additions, and most Canadian rows matched. In the admin, look up four vehicles you know (your own, a 2019 RAV4, a 2025 F-250 and a Honda Gold Wing) and check that the facts look right. Paste the report here if anything looks odd.

## Step 2: Classification rules, overrides and size variants

This step turns the facts into a class and a size variant for every model, adds Motorcycles as a seventh class, and adds the one lookup the booking form will call in Phase 3. Before you send it, check the third-row list I prepare; the task seeds from it.

**Claude Code task:**

> Phase 2, Step 2: classification. Follow docs/reference/vehicle-classification.md and decision 0060, and the facts loaded in Step 1.
>
> 1. **Rules.** An ordered list of rules, stored where decision 0060 says. Each rule has conditions on any stored fact (EPA size class, GVWR, curb weight, dimensions, drive, body style, make, model, year range) and gives a vehicle class; the first match wins. Seed the launch rules from the EPA-class mapping in data/vehicle-classes.yaml, then add weight and dimension rules for the known mismatches in the classification doc.
> 2. **Overrides.** A per-model override beats every rule; a per-vehicle override on a customer's vehicle beats both. Seed the per-model overrides named in the doc (Jeep Wrangler; Suburban, Expedition and Sequoia). Every override records who set it, when, and an optional note.
> 3. **Size variants.** Cars by doors, pickups by cab style (asked only when the model has more than one), crossovers and midsize SUVs by a third-row flag. The owner-approved third-row list is in `data/third-row-seating.yaml` (placed by the owner, not yet committed; commit it in this pull request). Seed the third-row flags from it first, then from NHTSA where it has data; "optional" and anything unknown is "ask". Match its make and model names to the catalog with the alias handling from Step 1, and list any row that matches no model in the report instead of guessing. The `ask_size` flag on `VehicleModel` says when the booking form must ask.
> 4. **Class settings** from `class_settings` in data/vehicle-classes.yaml. **Add a Motorcycles class** (a new decision, with the next free number): one price with no size variant, booked online, and a rule that sends every model with vehicle type motorcycle to it. Add one service to the price book, **Motorcycle Detail**, offered only for Motorcycles: a flat $100 with no condition level and no add-ons, one person, 1 hour of service time (2 hours on site with the 30-minute setup and breakdown, decision 0058), and the same jobs-per-day setting as Monthly Maintenance (two). Sales tax applies as usual, and the owner is authorized for it (decision 0061). Update the possible future classes in data/vehicle-classes.yaml: Oversized Vans & Trucks (full-size and fleet vans, trucks above the 350 series; they stay in their current classes until it exists), RVs (exterior only, priced per foot of length, which needs a new price basis), and Boats (a custom quote by size and work, outside the catalog).
> 5. **Preview.** A function that applies a proposed set of rules and overrides to the whole catalog without saving, and returns every model whose class or size variant would change, with old and new values and the rule responsible.
> 6. **Unclear models.** A model goes to a review queue instead of going live when no rule matches, two sources disagree on a fact a rule uses, or it straddles a threshold across its trims.
> 7. **The lookup.** One function, `classify(year, make, model, answers=None)`, returns the class, the size variant or the question still to ask, the price basis, the vehicle type, and how the answer was reached (rule, override, or review queue). Years before 1984 and models not in the catalog return the photo-card fallback from the doc, which now has seven cards, one of them Motorcycles. Note in docs/reference/booking-flow.md that motorcycle models appear in the same lists as cars, with a small label so a Honda Gold Wing and a Honda Accord are easy to tell apart.
> 8. **`python manage.py classify_vehicles`** applies the rules to the catalog, with `--dry-run` printing the preview. It never changes a model the owner set by hand.
> 9. **Tests** for rule order, both kinds of override, each size variant, the preview, the review queue triggers and the lookup, including the RAV4 example from decision 0065 and a motorcycle priced at $100 whatever the condition level. Update the classification doc, docs/reference/pricing.md, data/vehicle-classes.yaml and the price book data, and replace the note there that motorcycles are not classed.
>
> Open a pull request.

**You, after merging:**

```bash
sudo /srv/dixie-detail/ops/deploy.sh
sudo docker exec dixie-app-1 python manage.py load_pricebook
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data --source canada
sudo docker exec dixie-app-1 python manage.py classify_vehicles --dry-run
sudo docker exec dixie-app-1 python manage.py classify_vehicles
```

`load_pricebook` adds the Motorcycles class, its photo card and the Motorcycle Detail service, and puts the $100 price in a draft price book version. Publish that version from the control app's price book page with the current date; it adds only the motorcycle price, so no booked job changes. The Canadian rerun picks up matches the Step 2 changes made possible and reads from the download cache, so it needs the one-off container like Step 1.

**Check:** the report gives a count per class and a review queue count. Expect a long queue at first; Steps 3 and 4 are where it gets worked down. Read the launch rules in the pull request. They should read like the way you'd sort vehicles in your head; if any rule surprises you, say so before Step 3.

### Step 2 follow-up: fixes from the first dry run

The first `classify_vehicles --dry-run` (2026-10-22) showed a few problems:

- Some separate vehicles were merged under one model name, such as the Santa Fe Sport inside the Santa Fe.
- Some vehicles were listed twice under two spellings.
- Some three-row SUVs changed class from one model year to the next.
- Rules matched vehicles they weren't meant for.
- About 580 models went to the review queue, often because a few trims fell on the other side of a line.

You also settled two pricing choices that day: the full-size SUVs go with the Suburban, and every model that always has three rows is a Midsize SUV. Don't run `classify_vehicles` for real until this is merged.

**Claude Code task:**

> Phase 2, Step 2 follow-up: fixes from the owner's first `classify_vehicles --dry-run`. One pull request.
>
> 1. **Model names are the nameplates customers know.** The catalog groups EPA rows by base model, which merges different vehicles: Santa Fe Sport and Santa Fe XL into Santa Fe, Grand Cherokee L into Grand Cherokee, Atlas Cross Sport into Atlas, RX 350L and RX 450hL into RX, Outlander Sport and Outlander PHEV into Outlander, Encore GX into Encore, Range Rover Sport, Velar and Evoque into Range Rover, and Defender 90, 110 and 130 into Defender. Customers pick these as separate models, and several differ in seat rows. Either build model names from the EPA model name with drive and engine suffixes removed (2WD, 4WD, AWD, FWD, 4matic and similar, listed in data), or keep the base model and split it with a nameplate list in data. Explain the choice in the pull request. Overrides and owner-source models must still point at the right models. The import report lists every base model that is now split.
> 2. **One vehicle, one name.** The vPIC gap fill added models the EPA already has under another spelling, so they appear twice: EQB and EQB-Class, EQE and EQE-Class SUV, EQS and EQS-Class SUV, Wrangler and Wrangler/TJ, M-Class and ML-Class, F150 and F-150 Lightning, F250 and F-250. Keep one alias list in data and use it for import matching, for the Step 4 vehicle matching and for the third-row list. Merge the duplicates, and show the name customers expect (F-150, F-250, GLE). The report lists every merge.
> 3. **Full-size SUVs priced with the Suburban.** Add per-model overrides to Fullsize SUVs & Minivans for these: Chevrolet Tahoe, GMC Yukon and Yukon XL, Cadillac Escalade and Escalade ESV, Lincoln Navigator and Navigator L, Nissan Armada, Infiniti QX56 and QX80, Jeep Wagoneer, Ford Expedition MAX and EL, and Chevrolet Suburban HD. Add the Jeep Grand Wagoneer from 2022 on only; the 1984 to 1991 Grand Wagoneer is a different vehicle. Put them in data/vehicle-classes.yaml with the existing overrides.
> 4. **Three-row SUVs are Midsize SUVs in every year.** Add a rule above the EPA SUV rules: a model year marked "always" on the third-row list, with an SUV EPA class (small, standard, or the older special purpose class), is Midsize SUVs with three rows. Minivans and models with an override are unaffected. Then the Palisade, Telluride, CX-9, CX-90, Highlander, Pilot, Atlas and MDX keep one price across the years.
> 5. **Decide straddling trims by the majority.** The Highlander, Pilot, Atlas, MDX, Silverado and Sierra go to the review queue because a few trims fall on the other side of a condition. Decide by the condition most of a model year's trims meet. Queue the model only when there is no clear majority, with the threshold in data, starting at two-thirds. Show the split in the queue reason.
> 6. **Narrow two rules.**
>    - Rule 70, "Older SUVs over 4,500 lb", catches 2024 to 2026 Silverado and Sierra pickups. Limit the older-SUV rules to SUV classes and to the years the EPA used its special purpose class for SUVs.
>    - Rule 30, "Heavy pickups the EPA leaves out", catches minivans and light pickups such as the Astro, Caravan, Lumina APV, Dakota and Explorer Sport Trac. Limit it to models whose name has a heavy-duty series (2500, 3500, HD, Super Duty and similar, listed in data), or whose GVWR is over 8,500 lb.
> 7. **The report.** Add counts per class and per size variant. Add a section listing models whose year ranges end up in different classes, for the owner to look at in Step 4.
> 8. **The third-row list.** After items 1 and 2, the 27 rows the first dry run could not match should match. List any that still don't.
> 9. **Tests** for each example named above, and update the classification doc and the import guide.
>
> Open a pull request.

**You, after merging:** deploy. Then run the whole import again, because the model names are made during the import, not during classifying. It reads from the download cache, so it takes minutes. Then run the dry run:

```bash
cd /srv/dixie-detail
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data --dry-run
sudo docker compose run --rm --no-deps -v /srv/dixie-vehicle-data:/srv/vehicle-data app \
  python manage.py import_vehicle_data
sudo docker exec dixie-app-1 python manage.py classify_vehicles --dry-run
```

**Check:** the import report lists the base models it split (Santa Fe Sport, Grand Cherokee L, Atlas Cross Sport and others). The classify report no longer lists those as third-row rows that matched nothing. Once that's true, run `classify_vehicles` for real. The second dry run (2026-10-22 evening) found a few more small fixes; they are in the Step 3 task, and `classify_vehicles` can be run again after it.

## Step 3: Catalog screens in the control app

This step puts the catalog, the rules and the review queue on your phone, so the rest of Phase 2 (and every month after) is done there rather than at a terminal.

**Claude Code task:**

> Phase 2, Step 3: catalog screens in the control app, following decisions 0068 and 0069 and the existing control app layout. Signed-in users only; everything must work on a phone. **First, three classification fixes from the owner's second dry run:**
>
> - **(a) Model years the EPA hasn't published yet.** These are mostly next year's, which only vPIC lists so far, such as the 2027 F-150, RAV4, Highlander and Silverado. They take the class and size rule of the same model's nearest classified year, and the "how" line says so. They are classified again when the EPA data arrives. This keeps the monthly refresh from filling the review queue with every new model year.
> - **(b) The Jeep Wagoneer override starts in 2022.** The 1989 to 1990 Wagoneer is the old compact one.
> - **(c) Mercedes-Benz EQE and EQS sedan and SUV years are mixed** between "EQE"/"EQS" and "EQE SUV"/"EQS SUV". Put each year's SUV facts under the SUV name.
>
> 1. **Catalog search.** Pick year, make and model (typing narrows each list) and see the class, size variant, price basis, the facts from each source, and how the class was reached: which rule or override, or that it is waiting for review. A test price for a service from the price book on the same screen.
> 2. **Overrides.** From that screen, set or clear a per-model override for the class, the size variant or the third-row flag, with a note. A per-vehicle override is on the customer's vehicle screen.
> 3. **Rules.** The ordered list, written out in plain words (for example "EPA class Small Sport Utility Vehicle and curb weight over 4,000 lb → Midsize SUVs"). Add, edit, reorder and disable rules. **Saving always shows the preview first:** how many models change class or size variant, grouped by old and new class, with the list expandable, and nothing changes until the owner confirms.
> 4. **Review queue.** Each model shows why it is there, the facts that matter, and one tap to accept the suggested class, pick another, or set the size question. List the newest model years first. Filter by year and by reason. Let the owner select many items at once to accept their suggestions or send them to the photo card, since most of the queue is older vehicles. Show a count on the control app's home screen when the queue is not empty.
> 5. **Class settings** editable on their own screen, with the same preview when a change affects pricing.
> 6. **History.** Every change to a rule, an override, a class setting or a queue decision is recorded with who and when, and shown on the model's screen.
> 7. **Tests** for each screen's permissions, the preview-before-save on rules and class settings, and the queue actions. Update docs/operations/ with a short guide to the screens.
>
> Open a pull request.

**You, after merging:** deploy, then on the Pixel:

1. Look up your own vehicle and a 2019 RAV4. Check the class, the facts and the "how" line.
2. Open the rules, change one threshold slightly, and look at the preview. Cancel. Nothing should change.
3. Accept two items from the review queue, then check the history on one of them.

If a screen is hard to use one-handed, say what's awkward and I'll write a short follow-up task.

## Step 4: Link your vehicles and approve the job history

This is the step the roadmap's done test is about. Your imported vehicles were classed by hand in Baserow; now each one is matched to the catalog, and every difference comes to you.

**Claude Code task:**

> Phase 2, Step 4: link the imported vehicles to the catalog and add the approval list.
>
> 1. **Matching.** For each `Vehicle`, find its `VehicleModel` from year, make and model. Handle spelling differences ("Chevy", "Mercedes", "F150", trim words in the model field) with the alias list in data from the Step 2 follow-up; add aliases there, not in code. Never guess between two candidates: list them.
> 2. **`python manage.py link_vehicles`** with `--dry-run`, reporting: linked; not found; more than one candidate; and **class or size variant differs** between the vehicle as imported and the catalog. The report shows vehicle IDs, year, make, model and color only, never customer names.
> 3. **Nothing in the past changes,** with one exception. Linking sets `vehicle_model` and fills `missing_details` where it can. A vehicle's class changes only when the owner accepts the catalog's class on screen, and quoted prices on past appointments stay as they are (decision 0059). The exception, at the owner's request: the two past motorcycle appointments, imported with no class, get the Motorcycles class and the Motorcycle Detail service. Their recorded amounts and payments stay as imported, because they are already in the books (decision 0066); the report lists either one whose amount is not $100 so the owner can decide.
> 4. **Differences screen** in the control app: for each vehicle that differs, one tap to keep the imported class (as a per-vehicle override, for a lifted or modified vehicle), accept the catalog's class, or set a per-model override for every vehicle of that model.
> 5. **Approval list.** One screen listing every distinct model in the job history, plus a spot-check list kept in data. Propose about 30 models that sit near a boundary: Wrangler, Bronco, 4Runner, Tahoe and Suburban, Sequoia, RAV4, CR-V, Outback, Crosstrek, Model Y, Highlander, Telluride, Tacoma, F-150 and F-250, Ram 1500 and 2500, Sienna, Odyssey, Transit, Sprinter, Lexus RX, Outlander, Sorento, Santa Fe and similar. Also include every model the classify report lists under "years in different classes". Show each model once with all its year ranges, each range's class, size rule and how it was reached, and Approve or Change per range. Record who approved what and when. A later change to the rules or overrides that affects an approved model clears its approval and shows it again.
> 6. **Tests** for the aliases, the never-guess rule, the three choices on the differences screen and approvals being cleared by a change. Update the docs.
>
> Open a pull request.

**You, after merging:**

```bash
sudo /srv/dixie-detail/ops/deploy.sh
sudo docker exec dixie-app-1 python manage.py link_vehicles --dry-run
sudo docker exec dixie-app-1 python manage.py link_vehicles
```

Then, on the Pixel:

1. Work through "not found" and "more than one" first. Most are fixed by an alias; tell me the spelling and I'll write the line for Claude Code. Check that the two motorcycles now show Motorcycles and Motorcycle Detail.
2. Work through the differences screen.
3. Add any models you want to the spot-check list, then approve the whole approval list. When you change a class there, think about whether it is one vehicle (per-vehicle override), every one of that model (per-model override), or a pattern (a rule, which shows the preview).

### Step 4 follow-up: fixes from the first link dry run

The first `link_vehicles --dry-run` (2026-10-24) linked 15 vehicles and left 114 unlinked:

- **77** have a make and model but no year. The matching needs a year, so none of them linked, and their models would be missing from the approval list.
- **18** have no make or model at all, and **16 more** have a make only. These stay flagged for an update at the next visit.
- **2** are the Harley jobs, recorded with make "Harley" and no model.
- **1** is a 2014 Dodge Ram. From 2011 the truck is sold as the Ram 1500, under the make Ram.

**Claude Code task:**

> Phase 2, Step 4 follow-up: fixes from the owner's first `link_vehicles --dry-run`. One pull request.
>
> 1. **Link vehicles with no year by make and model.** When a vehicle has no year but its make and model match exactly one catalog model, link it. Keep the class and size variant it was imported with, and leave the year flagged in `missing_details` for the next visit. Show these in the report as "linked, year unknown". They are not compared on the differences screen, because the class depends on the year.
> 2. **The approval list uses make and model,** so a job-history model is on it whether or not its vehicles have a year. A model with year-less vehicles shows all its year ranges.
> 3. **Aliases** in data/vehicle-names.yaml:
>    - Harley and Harley Davidson mean Harley-Davidson.
>    - Dodge Ram from 2011 on means the Ram 1500, and Dodge Ram 2500 from 2011 on means the Ram 2500. Allow an alias to apply only to certain years.
>    - Chevrolet 2500 means the Silverado 2500 HD.
>    - Ignore the trim words King Ranch and 392.
>    - GX550 means the Lexus GX, and CLS 550 the Mercedes-Benz CLS.
>    - Map 530i and 650i to the catalog's BMW names.
>    - Mazda 6 means the catalog's Mazda 6.
>    - Make every match ignore case and spacing, as in Rav4 and Expedition Max.
> 4. **Motorcycles by make.** A vehicle whose make makes only motorcycles (Harley-Davidson, Indian, Ducati and the other motorcycle-only makes in data/vehicle-data-import.yaml) gets the Motorcycles class even with no model. Apply the motorcycle-job change from Step 4 to the two Harley appointments.
> 5. **A name check in the report:** for every unlinked vehicle that has a make and model, say whether the name would match once a year is known. Then a spelling problem can't hide behind a missing year.
> 6. **Tests** for each item and each alias above.
>
> Open a pull request.

**You, while it's being built (optional):** if you know the year of any of the 77, fill it in on the vehicle's screen in the control app. Those vehicles then link fully, with a class check.

**You, after merging:** deploy, run `link_vehicles --dry-run` again and paste the report here before running it for real. The two vehicles on the differences screen (the 2016 Sorento and the 2026 Murano) are pricing decisions for you, not errors. Settle them on that screen after the real run.

## Step 5: Monthly refresh

New model years appear through the year, so the catalog re-pulls its sources once a month. Clean results go live on their own; anything unclear waits in the review queue.

**Claude Code task:**

> Phase 2, Step 5: monthly vehicle data refresh, following the pattern of the backup and public health timers in ops/ and docs/architecture/backups-and-monitoring.md. **First, three leftovers from Step 4:**
>
> - **The Mercedes-Benz CLS alias.** "CLS 550" points to a catalog name that doesn't exist. Point it at the catalog's real CLS model name.
> - **"Ram Ram 1500" in the `link_vehicles` report.** The text repeats the make; fix it.
> - **Display names in the catalog's own capitalization.** Show names as the maker writes them, not as the source spells them: 350Z, not 350z. Do this through the alias list, and list every name it changes.
>
> 1. **`ops/vehicle-refresh.sh`** runs `import_vehicle_data --source all --refresh`, then `classify_vehicles`, in a one-off app container with the download cache attached, exactly as docs/operations/importing-vehicle-data.md does by hand, and pings a new Healthchecks check: start, then success or failure with a one-line summary (models added, changed, sent to the queue). Have deploy.sh create the cache folder with the right owner if it is missing, so a rebuilt server needs no manual step.
> 2. **`dixie-vehicle-refresh.service` and `.timer`,** installed by deploy.sh like the others. Run it on the first Sunday of each month at 4:15 AM Eastern, with a random delay of up to 15 minutes, so it never lands on the 2:45 AM backup or a business day. It fetches its Bitwarden secrets in one call per run and retries a 429, as the backup does since the fix in pull request #29.
> 3. **What a refresh may change on its own:** add new models and model years that the rules classify cleanly, and update facts. **What it may not:** change the class or size variant of a model that has an override or an approval, or of any model in the job history. Those go to the review queue with the old and new values. Models that disappear from a source are kept and marked with the date last seen, never deleted.
> 4. The control app's home screen shows the last refresh (date, result, counts) next to the review queue count.
> 5. Name the new Bitwarden secret for the ping URL to match the existing check secrets, and document it, the timer and what to do when the check fails in docs/operations/monitoring.md. Add the timer to the server docs. Tests for the rule in item 3.
>
> Open a pull request.

**You, before merging:**

1. In Healthchecks, create a check named "Vehicle data refresh" with a cron schedule matching the timer, in the America/New\_York time zone, and a grace period of 6 hours.
2. Save its ping URL in Bitwarden Secrets Manager under the name the pull request gives.

**You, after merging:**

```bash
sudo /srv/dixie-detail/ops/deploy.sh
systemctl list-timers 'dixie-*'
sudo systemctl start dixie-vehicle-refresh.service
journalctl -u dixie-vehicle-refresh.service -n 30
```

**Check:** the timer's next run is a first Sunday of the month at about 4:15 AM, the manual run ends with nothing new (you imported days ago), and the Healthchecks check is green.

## Side task: Size-based vehicle classes (before Step 6)

Decided 2026-10-26: cars, wagons, crossovers, SUVs and minivans are classed by measured size (box volume), not by body type. This replaces Coupes & Sedans, Crossovers & Wagons, Midsize SUVs and Fullsize SUVs & Minivans. The vehicle size report showed why: these vehicles form one continuous size range, and EPA's labels cut across it. Hold Step 6 until the new classes are applied, so the approval list is redone only once.

| Class (working name) | Rule | Size variant |
| --- | --- | --- |
| Motorcycles | Unchanged | Flat price |
| Light Pickups | Pickups as today's rules find them; "& Offroad" dropped | Cab: 1 or 2 |
| Fullsize Trucks | Unchanged | Cab: 1 or 2 |
| Small | Box volume under 490 cu ft | 1 (two-seaters) or 2 rows |
| Medium | 490–579 cu ft; every 3-row vehicle starts here | 2 or 3 rows |
| Large | 580–699 cu ft (minivans land here) | 2 or 3 rows |
| Full-size | 700–864 cu ft | 3 rows |
| Full-size Vans | 865 cu ft and up; ask for a quote until priced | None |

Seat rows come from data: 1 for EPA two-seaters, 3 (or ask, for an optional third row) from the third-row list, otherwise 2. Doors are no longer used. Two steps: **A** builds the rules and shows what they would do, changing nothing. Then you set prices, and **B** applies the classes.

**Claude Code task (A):**

> Phase 2 side task A: size-based vehicle classes, rules and dry run only. One pull request.
>
> The owner decided (2026-10-26) to class cars, wagons, crossovers, SUVs and minivans by measured size instead of body type, based on the vehicle size report. EPA labels proved unreliable for this: two-wheel-drive small crossovers are EPA cars or station wagons, the Murano changed EPA label between generations, and battery weight puts small EVs over the 6,000 lb rating. This task builds the new rules and a dry run. It does not change any vehicle record, classification, override, approval, appointment or published pricebook.
>
> 1. **Box volume as a stored fact.** For each model year with dimensions: length × width × height ÷ 1,728 in cubic feet, the median across trims, as the size report computes it. A model year without dimensions takes the value of the nearest measured model year of the same model (the newer one on a tie), marked "inherited from \<year>".
> 2. **New rules as data, in this order.** Use the existing ordered-rule and preview machinery and add the box-volume condition it lacks. Keep the lines (490, 580, 700, 865) as settings in one data file, not in code.
>    - Motorcycles: unchanged.
>    - Pickups: identified as the current rules do, keeping today's Light Pickups and Fullsize Trucks split. Rename Light Pickups & Offroad to Light Pickups. Check that the Hyundai Santa Cruz and Ford Maverick are treated as pickups.
>    - Full-size Vans: box volume 865 and up. Class setting: ask for a quote, not bookable online.
>    - Full-size: 700 to under 865.
>    - Large: 580 to under 700.
>    - Medium: 490 to under 580, plus every 3-row vehicle under 490.
>    - Small: under 490.
> 3. **Seat rows as data:** 1 for the EPA Two Seaters class; 3 for "always" and ask for "optional" in the third-row data, as today; otherwise 2. Pickups keep cab type. Doors are no longer used.
> 4. **No measurements in any year:** fall back to the class where most measured model years of the same EPA size class land. Compute that table and print it. With no dimensions and no EPA class, leave the model unclassified, as unclassified models are handled today.
> 5. **Classes are pricebook records.** If the engine needs Small, Medium, Large, Full-size and Full-size Vans to exist, add them to an unpublished draft pricebook version with no prices. Publish nothing and do not retire the old classes yet.
> 6. **Old overrides and approvals are not carried forward.** They name the old classes. The new rules replace the full-size SUV override list and the always-3-row rule.
> 7. **`classify_vehicles --scheme size --dry-run`** prints the following and changes nothing:
>    - model years per new class and per source (measured, inherited, EPA-class fallback, unclassified), and the fallback table;
>    - the near-line list: every model within 5 cu ft of a line (its newest size range from 2015 on, plus any range a customer owns), with its box volume and the classes on each side;
>    - models whose class changes between model years, as year ranges;
>    - every existing override and approval, with what the new rules give instead;
>    - customer vehicles: recorded class, new class and the reason. A vehicle linked with no year gets a class when all its model's years land in one class; otherwise list it as "year needed" with the classes its years span. An unlinked vehicle gets a proposed class from its recorded class, marked for review: Coupes & Sedans to Small; Crossovers & Wagons to Medium; Midsize SUVs to Large; Fullsize SUVs & Minivans to Full-size, or Large for a minivan; pickups and motorcycles unchanged. Show vehicle ids and year, make and model only, never customer names;
>    - the non-pickup models now in Light Pickups & Offroad, with their new classes;
>    - a pickup ladder for placing a pickup size line later: every pickup model's newest size range from 2015 on plus customer-owned ranges, sorted by box volume, with length, cab types, EPA class, GVWR range, current class and customer counts, and the five largest steps in box volume and in length. Do not change the pickup rules.
> 8. **Docs:** a new decision record (next free number) for size-based classes. It supersedes the parts of earlier decisions it replaces: body-type classes, cars priced by doors, the full-size SUV override list and the always-3-row rule. Find those decisions and link them. Update the vehicle classification guide (status draft until the classes are applied) and the data files. Do not change data/price-matrix.csv yet. US English; no customer names.
> 9. **Tests:** box-volume median and inheritance; rule order and line edges (489.9 vs. 490.0, and so on); the 3-row floor; seat rows; the EPA-class fallback; the year-less vehicle logic; the dry run changes no rows.
>
> Open a pull request.

**You, after it merges:** deploy, then save the dry run in your home folder on the server.

```bash
sudo /srv/dixie-detail/ops/deploy.sh
sudo docker exec dixie-app-1 python manage.py classify_vehicles --scheme size --dry-run > ~/size-classes-dry-run.txt
```

Then on Fedora, copy it into your private folder and remove the server copy:

```bash
mkdir -p "$HOME/Dixie Detail/reports"
scp 'USER@192.0.2.10:size-classes-dry-run.txt' "$HOME/Dixie Detail/reports/"
ssh USER@192.0.2.10 'rm ~/size-classes-dry-run.txt'
```

**Check:** the near-line list is about two dozen models, the Santa Cruz and Maverick are pickups, minivans are in Large, the Tahoe and its rivals are in Full-size, and the ProMaster, Transit and Sprinter are in Full-size Vans. Then attach the dry run here. It holds vehicle ids and year, make and model, but no customer names. We'll go through the near-line models, the old overrides and the customer vehicles.

**Then prices.** A simple starting point copies today's prices: Small from Coupes & Sedans, Medium from Crossovers & Wagons, Large from Midsize SUVs, and Full-size from Fullsize SUVs & Minivans. Change what you want from there. Task B, written once prices are set, publishes the new pricebook version and applies the classes. It also reviews booked jobs, adds photo cards for the new classes and retires the old classes.

### Dry run A results and decisions (2026-10-26)

The dry run passed most of the checks:

- 22 models sit near a line.
- The Santa Cruz and Maverick are pickups.
- Minivans are in Large.
- The Tahoe, Suburban, Yukon, Expedition, Sequoia, Navigator, Armada, QX80 and Wagoneer are in Full-size.
- The Transit is in Full-size Vans.

It also showed three problems:

- **The Ram ProMaster 2500 and 3500 were treated as pickups** (they appear on the pickup ladder).
- **The EPA label splits midsize pickups** between Light Pickups and Fullsize Trucks.
- **A few models switch class for a few years and then switch back,** because of small measurement differences between trims.

**The owner decided:**

1. **A pickup size line at 760 cu ft.** Every midsize pickup is Light Pickups. The Rivian R1T, Cybertruck, half-tons and heavy-duty trucks are Fullsize Trucks. The line sits in the ladder's gap between the 2025 Canyon (745) and the R1T (774).
2. **Smooth short swings.** A run of up to 6 model years between two runs of the same class takes that class. Examples: the Escalade 2009–2014, Explorer 2004–2005, Audi Q8 2024–2025, Range Rover 2022 and Mercedes S-Class.
3. **Customer vehicles with no year get the class of their model's newest generation,** flagged so the year is confirmed at the next visit.
4. **Big sedans stay in Medium.** Size decides, so the Charger, Challenger, Impala, Model S and others price with the small crossovers.

**Confirmed by the owner (2026-10-27):** the near-line models keep their measured class, with three overrides for consistency:

- the Audi Q4 e-tron 2022–2026 goes to Medium, to match its sister vehicle, the ID.4;
- the Porsche Cayenne 2026 goes to Large, like 2019–2025;
- the BMW iX 2026 goes to Medium, like 2022–2025.

These go into Task B, along with this fix: vans (ProMaster, Transit, Sprinter, Express, Savana, E-Series, NV) are identified before the pickup rules, so they land in Full-size Vans or by size, never in pickups.

### Prices (2026-10-27) and Task B

You set the prices in your pricing sheet on 2026-10-27, and two more decisions came with them:

- **Monthly and Quarterly Maintenance take the Full Detail hours** for the same class and rows, as before. The sheet had carried over old maintenance hours for Medium, Large and both pickup classes.
- **The Motorcycle Detail is 2 hours of service** (3 on site), still $100 with no condition level and no add-ons.

Full-size Vans have no prices: they are quote-only.

The price book file is `price-matrix.csv`, 91 rows in the repo's format: service, vehicle class, size variant, one-person service hours, price. It renames Fullsize Trucks to Full-size Trucks, to match the sheet.

**Before sending Task B,** save `price-matrix.csv` over `data/price-matrix.csv` in your copy of the repo. Don't commit it; the task commits it.

**Claude Code task (B):**

> Phase 2 side task B: apply the size-based vehicle classes and the new price book. One pull request. The owner has replaced data/price-matrix.csv with the new price book (uncommitted; commit it in this pull request). Read the size-classes decision record and the runbook notes from dry run A.
>
> 1. **Rule changes in data/size-classes.yaml:**
>    - **Vans before pickups.** Identify vans (ProMaster, Transit, Sprinter, Express, Savana, E-Series, NV and similar, listed in data) before the pickup rules. Large vans land in Full-size Vans by size, small vans (Transit Connect, ProMaster City, NV200, Metris) by size like any other vehicle, and no van is ever a pickup.
>    - **A pickup size line at 760 cu ft.** Pickups under 760 are Light Pickups, 760 and up Full-size Trucks. A pickup with no box volume in any year falls back to the EPA label: small pickups to Light Pickups, standard pickups and heavy-duty trucks to Full-size Trucks.
>    - **Rename Fullsize Trucks to Full-size Trucks.**
>    - **Smoothing.** A run of up to 6 model years between two runs of the same class takes that class. The report lists every smoothed run.
>    - **Three per-model overrides:** the Audi Q4 e-tron 2022–2026 goes to Medium, the Porsche Cayenne 2026 to Large, and the BMW iX 2026 to Medium.
>    - **Customer vehicles with no year** take the class of their model's newest generation, flagged so the year is confirmed at the next visit.
> 2. **Price book.** data/price-matrix.csv now prices Small, Medium, Large, Full-size, Light Pickups, Full-size Trucks and Motorcycles. `load_pricebook` loads it as a draft version.
>    - Full-size Vans: booking set to ask for a quote, with no prices.
>    - The Motorcycle Detail is 2 hours of service.
>    - Add a check, run by `load_pricebook` and the tests, that refuses a price book where any of these fail: Monthly is 50% and Quarterly 80% of Full Detail for the same class and rows; maintenance hours equal Full Detail hours; and every class and row count the rules can produce has a Full Detail price, except quote-only classes.
> 3. **Apply in one step:** `python manage.py apply_size_classes --effective YYYY-MM-DD`, with `--dry-run`. It does all of the following in one transaction, so the classes and the prices never disagree:
>    - publishes the draft price book with that effective date;
>    - switches every model year to the size-based classes;
>    - retires the body-type classes. Retired classes are kept for history (past appointments and their quote lines keep the class they had), hidden from booking, quoting and the catalog.
>    - archives the old rules, overrides and approvals. They stay in history but are no longer active.
> 4. **Customer vehicles.** Set each vehicle's class as the size dry run reported, including the newest-generation rule. Vehicles with no model, whose class is only proposed from their recorded class, go on the differences screen for the owner.
> 5. **Booked jobs.** Every future appointment keeps its quoted price, which is the price of record (decision 0059). The existing booked-job review lists each one with its quoted price and its price under the new book, so the owner can choose. Nothing changes without the owner.
> 6. **Photo cards** for every class except Full-size Vans, which gets a "send us a photo for a quote" card. Each card shows the class name, a few example models kept in data, and a placeholder until the owner adds a photo:
>    - Small: Civic, Corolla, Camry, Accord, Crosstrek
>    - Medium: RAV4, CR-V, Equinox, Rogue, Sorento
>    - Large: Highlander, Pilot, Explorer, Odyssey, Sienna
>    - Full-size: Tahoe, Yukon, Expedition, Suburban, Sequoia
>    - Light Pickups: Tacoma, Colorado, Frontier, Ranger, Maverick
>    - Full-size Trucks: F-150, Silverado, Ram 1500, Tundra, F-250
>    - Motorcycles: unchanged
> 7. **The approval list starts over.** It lists the job-history models plus a new spot-check list. Put on it every near-line model, plus the 2024+ Tacoma, 2025+ Canyon, Rivian R1T, Escalade, 2020+ Highlander, 2025+ Murano, Wrangler, Bronco, Tahoe before 2007 and Suburban before 1998.
> 8. **The monthly refresh** classifies new model years with the size rules.
> 9. **Docs and data:**
>    - Mark the size-classes decision record applied.
>    - Set the vehicle classification guide to current, and rewrite data/vehicle-classes.yaml for the size-based classes, with the body-type classes listed as retired.
>    - Update docs/reference/pricing.md and the class names everywhere, including Full-size Trucks.
>    - Fold in the close-package items from Step 5 if they aren't done: `deploy.sh` enables the refresh timer, and the refresh log prints only its summary and newly queued models.
>    - US English; no customer names.
> 10. **Tests** for:
>     - the van and pickup order, and the 760 line edges;
>     - smoothing;
>     - the three overrides;
>     - the newest-generation rule;
>     - the price book check;
>     - the one-transaction apply, including that a dry run changes nothing;
>     - retired classes staying on past appointments.
>
> Open a pull request.

**You, after it merges:**

```bash
sudo /srv/dixie-detail/ops/deploy.sh
sudo docker exec dixie-app-1 python manage.py load_pricebook
sudo docker exec dixie-app-1 python manage.py classify_vehicles --scheme size --dry-run > ~/size-classes-dry-run.txt
sudo docker exec dixie-app-1 python manage.py apply_size_classes --effective YYYY-MM-DD --dry-run
```

Use today's date (or the date you want the new prices to start) for `YYYY-MM-DD`. Copy the size dry run to your Fedora machine as you did for dry run A, and send me both outputs. In the new dry run, check that:

- the ProMaster and Sprinter are in Full-size Vans;
- every midsize pickup is in Light Pickups;
- the 2009–2014 Escalade is Full-size.

After I've looked, run `apply_size_classes` without `--dry-run`. Then, in the control app:

1. Go through the booked-job review.
2. Go through the differences screen.
3. Approve the new approval list.

After that comes Step 6.

### Task B follow-up: fixes from the first apply dry run (2026-10-28)

Task B merged, along with a fix for a crash on a booked job with no vehicle. The size dry run is now part of `apply_size_classes --effective DATE --dry-run`, and `classify_vehicles` no longer takes `--scheme`. The first apply dry run **refused**: the price book check found Full-size vehicles with 2 rows and a 1990–1991 Mercedes 500 two-seater in Medium. Reading the report also showed:

- **Minivans got 2 rows.** For example, your two Odysseys came out as Large, two rows.
- **Older full-size pickups measure under the 760 line,** so the F-150 before 2006, the Silverado, Sierra and Tundra before 2007, and older HD trucks are Light Pickups. **You decided to keep that (2026-10-28):** the detail work goes by size, so a smaller older truck is priced as a Light Pickup.
- **Most full-size vans aren't in Full-size Vans.** Only the Transit, ProMaster and Mercedes Sprinter were caught. The Express, Savana, E-Series and Econoline, Ram Van and Dodge Sprinter land in Full-size, Large or the review queue.
- **Smoothing turned the Escalade the wrong way:** 2007–2014 came out Large instead of Full-size.

**Claude Code task:**

> Phase 2, Task B follow-up: fixes from the owner's first `apply_size_classes --dry-run`. One pull request. The price book does not change.
>
> 1. **Seat rows.**
>    - Full-size is always 3 rows.
>    - The EPA minivan classes, and the minivans in a list in data for models with no EPA class, are always 3 rows.
>    - One row exists only in Small: a two-seater that measures into a larger class counts as 2 rows.
> 2. **Pickups stay pickups in every year.** A model that is a pickup in any model year is a pickup in all of them. The 760 cu ft line then decides between Light Pickups and Full-size Trucks, so a pickup is never Large or Full-size. The dry run had two cases: the Tundra 1995–1999 came out Large and the Titan 2002–2003 Full-size. Older full-size pickups that measure under 760 stay Light Pickups; that is the owner's decision (2026-10-28), not a bug.
> 3. **Full-size vans by nameplate.** These are Full-size Vans in every model year, whatever they measure, from a list in data: Express (Cargo and Passenger), Savana (Cargo and Passenger), E-Series, E-150, E-250, E-350 and Econoline, Ram Van and B-series vans, G-series vans and Vandura, Sprinter and eSprinter of every make, Transit except Transit Connect, ProMaster except ProMaster City, and NV1500, NV2500 and NV3500. Small vans (Transit Connect, ProMaster City, City Express, NV200, Metris) still go by size.
> 4. **Escalade.** Add an override for the Cadillac Escalade 2007–2014 to Full-size, like the Tahoe and Yukon of those years. In the report, list any smoothing that moves a run away from the class of the newest generation, so a backwards smooth like this one is easy to spot.
> 5. **Tests** for each rule, including:
>    - an Odyssey and a Sienna get 3 rows;
>    - the 1995–1999 Tundra and 2002–2003 Titan are pickups, and a 2004 F-150 under 760 cu ft stays Light Pickups;
>    - a 2010 Express and a 2008 E-250 are Full-size Vans;
>    - the 1990 Mercedes 500SL is Medium with 2 rows.
>
>    Update the docs and data/size-classes.yaml.
>
> Open a pull request.

**You, after it merges:** deploy, then run the apply dry run again and send me the file, as before:

```bash
sudo /srv/dixie-detail/ops/deploy.sh
sudo docker exec dixie-app-1 python manage.py apply_size_classes --effective YYYY-MM-DD --dry-run > ~/size-apply-dry-run.txt
```

The price book draft stays as it is, so there's no need to run `load_pricebook` again.

**Second apply dry run (2026-10-28 evening):**

- **Fixed:** vans by nameplate (Full-size Vans now 604 model years), minivans at 3 rows, the Escalade Full-size from 2007, and the Tundra a pickup in every year.
- **Still refused once:** 14 old minivans (the 2008–2009 Mazda5, the 1984–1991 Dodge Caravan and others) measure Small with 3 rows. The 3-row floor ran before the minivan rule set their rows.
- **The fix,** a one-line Claude Code task: apply the floor after seat rows are final.
- **Accepted as is:** the 11 pre-2005 runs that smoothing moved away from the newest generation, which fit the size-first rule.

After that fix, one more dry run, then the real `apply_size_classes --effective DATE`. Then attach the vehicle to the booked job on 2026-11-28, and in the booked-job review keep the quoted prices but take the new hours.

## Step 6: Acceptance

**The done test**, on the Pixel:

1. The approval list shows every job-history model and every spot-check model approved, with nothing left.
2. Catalog search gives the answer you expect for each of these:
   - a Camry (Small, 2 rows) and a Mazda MX-5 (Small, 1 row);
   - a RAV4 (Medium, 2 rows) and a 2022 Sorento (Medium, 3 rows);
   - a 2016 Sorento (Medium; asks about the optional third row);
   - a 2022 Highlander and an Odyssey (Large, 3 rows);
   - a Tahoe and a 2010 Escalade (Full-size, 3 rows);
   - a 2024 Tacoma (Light Pickups) and a 2024 F-150 (Full-size Trucks), each asking about the cab, and a 2004 F-150 (Light Pickups, by size);
   - a Transit or Express (Full-size Vans: a quote card, no price);
   - a Honda Gold Wing (Motorcycles, $100 at any condition level);
   - a 1979 vehicle and a made-up model (the photo cards).
3. A test price for one service on a vehicle in each class matches the price matrix.
4. The review queue is empty, or holds only models you have chosen to leave for later and none from your job history.

Then on the server, because Phase 2 added tables: `sudo systemctl start dixie-backup.service`, then `sudo /srv/dixie-detail/ops/restore-test.sh`. It should pass.

**Closing the phase.** When all of that passes, tell me. I'll freeze this runbook and give you a close package like Phase 1's, for one Claude Code pull request that:

- marks Phase 2 done in data/phases.yaml and the roadmap, with the pull request numbers;
- sets the three vehicle data sources in data/integrations.yaml to "Working";
- adds this runbook to docs/operations/ as a historical record;
- moves vehicle-classification.md from planned to current;
- makes deploy.sh enable dixie-vehicle-refresh.timer like the other timers, if Step 5's fix didn't already (on 2026-10-24 it had to be enabled by hand);
- makes the refresh's journal print only its summary and newly queued models, not the whole review queue.

After that merges, publish the portfolio from the workstation:

```bash
cd ~/Projects/Dixie-Detail
git switch main && git pull
tools/publish-portfolio.sh
```

Read the review list and the commit titles before answering `y`. I'll update the project brief, and Phase 3 (the booking form) is next.

## Decisions settled for Phase 2

Settled on 2026-10-22 and already written into the tasks above.

**1. No new price factors in v1.0.** A price still comes from the vehicle class, the size variant and the condition level. Three things are planned for later, and none of them needs anything built now beyond what Phase 2 already collects:

| Later addition | What it will take |
| --- | --- |
| Oversized Vans & Trucks (full-size and fleet vans, trucks above the 350 series) | A new class, a rule on GVWR or model (Step 1 already stores GVWR), and prices. All of it is screen and data work after Phase 2; the preview shows exactly what moves. Until then those vehicles stay in their current classes. |
| RVs: exterior only, priced per foot | A new class, a "per foot" price basis (a small code change), the exterior services, and a length question on the booking form. |
| Boats: a custom quote by size and work | Not part of the vehicle catalog. A quote request on the booking form, planned with Phase 3 or later. |

**2. I prepare the third-row list** of crossovers and midsize SUVs sold since about 2010, each marked "always", "optional" or "never" by model years. When I'm not sure, I'll mark it "optional", which means the form asks: one extra question beats a wrong price. You check the list before sending Step 2.

**3. Motorcycles become a vehicle class now.** Motorcycle Detail is a flat $100 with no condition level and no add-ons, and takes 2 hours on site (1 hour of service plus the 30-minute setup and breakdown). It allows two jobs a day, like Monthly Maintenance; you can change that setting later. Motorcycle models come from NHTSA and appear in the same year, make and model lists as cars, with a small label. The two past motorcycle jobs get the class and the service, and their recorded amounts stay as they were paid. RVs are planned as above, and are not built in Phase 2.
