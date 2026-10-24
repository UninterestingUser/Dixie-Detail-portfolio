---
id: 81
title: "The vehicle data is refreshed on the first Sunday of each month, and a refresh never changes the class of a model the owner relies on"
summary: "A monthly timer reloads the EPA, vPIC and Canadian data and reclassifies; class or size changes to models with an override, an approval or jobs wait in the review queue."
date: 2026-10-24
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-24
supersedes: []
superseded_by: []
related: [docs/decisions/0071-vehicle-facts-per-model-year-and-source.md, docs/decisions/0070-nightly-backup-at-2-45.md, docs/decisions/0079-approval-list.md, docs/operations/monitoring.md, docs/operations/importing-vehicle-data.md, docs/reference/vehicle-classification.md, ops/vehicle-refresh.sh, ops/dixie-vehicle-refresh.timer]
---

# 0081: The vehicle data is refreshed on the first Sunday of each month, and a refresh never changes the class of a model the owner relies on

**Status:** accepted · **Date:** 2026-10-24 · **Area:** vehicles

## Context

The EPA adds models as it tests them, and NHTSA vPIC adds models through the year, so a catalog loaded once goes stale: next year's models would stay off the booking form's lists. Until now the import and the classification were run by hand ([importing-vehicle-data.md](../operations/importing-vehicle-data.md)). Running them unattended raises one question the hand run never had: what may the machine change without the owner looking? The owner has approved classes on the approval list, set model overrides, and quoted customers by class; a fact the EPA corrects should not quietly move a customer's SUV to another price.

## Decision

1. **A monthly refresh.** `dixie-vehicle-refresh.timer` starts `dixie-vehicle-refresh.service` on the first Sunday of each month at 4:15 AM Eastern, plus a random delay of up to 15 minutes. Sunday is not a business day, and 4:15 AM is well clear of the 2:45 AM backup (decision 0070). The timer has no `Persistent=`: a refresh missed while the server was off waits a month rather than running at boot on a business day.
2. **The same commands as by hand.** `ops/vehicle-refresh.sh` runs `refresh_vehicle_data` in a one-off app container with the download cache attached. That command runs `import_vehicle_data --source all --refresh`, then, if the import succeeded, `classify_vehicles --refresh`, and records the refresh (start, end, result, models added and changed, model years sent to the review queue, class changes held).
3. **What a refresh may change on its own:** add new models and model years, which go live when the rules classify them cleanly; update facts; and change the class of a model nothing protects.
4. **What a refresh may not change:** the vehicle class or size variant of a model year that is already live, when its model has a model override, an approval on the approval list, or customers' jobs (the approval list's job history). That model year goes to the review queue under the reason "Held by the monthly refresh", keeping its class meanwhile, with the old and the new class and size in the reason and the new one as the suggestion. It stays held until the owner settles it, even after the hold clears the model's approval. It leaves the queue by itself only if the facts change back.
5. **Nothing is deleted.** A model or model year a source stops listing is kept, with the date the source last listed it (decision 0071).
6. **Monitoring.** A third Healthchecks.io check, "Vehicle data refresh", gets a start ping, then a success or failure ping whose first line is the refresh's one-line summary. Its ping address is the Bitwarden secret `HEALTHCHECKS_VEHICLE_REFRESH_URL`, named like the other two, and the script fetches it in one Bitwarden call per run, retrying a 429 as the backup does. The control app's home screen shows the last refresh next to the review queue count.
7. **The cache folder is created by `ops/deploy.sh`** when it is missing, owned by the app container's user, so a rebuilt server needs no manual step.

## Alternatives considered

- **Hold every class change, protected or not.** The review queue would fill with models no customer has booked, and the owner would approve changes nobody relies on.
- **Apply every class change and only report it.** A quote could change between the owner approving a class and the customer booking, with nothing asking the owner first.
- **Run the refresh weekly.** The sources change slowly; each full run makes about 3,500 vPIC calls.
- **Run it at boot after a missed month.** That could land on a business day, during bookings.
- **Avoid the public health check's 10-minute marks, as the backup does.** The random delay the owner asked for makes that impossible; a 429 from Bitwarden is retried instead (`ops/lib/bws.sh`).

## Consequences

New models reach the booking form within about a month of a source listing them. A held change waits for the owner, so a model in the job history can show its old class for a while after the EPA changes its facts; the review queue and the home screen say so. A rule or override the owner changes in the control app, or `classify_vehicles` run by hand, applies the rules as they are, because the owner sees the preview first. A failed refresh leaves facts already written by the sources that succeeded; the next run, or one started by hand, picks up from there.
