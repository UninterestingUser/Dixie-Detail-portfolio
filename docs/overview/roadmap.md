---
title: Roadmap and phase status
summary: The eight build phases, what each delivers, the test that ends it, and where the project stands now.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-11-19
tags: [roadmap, phases, status]
related: [data/phases.yaml, docs/operations/phase-0-foundations-runbook.md, docs/operations/phase-1-core-data-runbook.md, docs/operations/phase-2-vehicle-catalog-runbook.md, docs/operations/phase-3-scheduling-and-website-runbook.md, docs/decisions/README.md]
---

# Roadmap and phase status

The booking path ships first because it earns money; the back-office features follow once real data is flowing. Each phase becomes a GitHub milestone, and each task an issue. A phase ends when the owner runs its test and it passes. The structured list is in [data/phases.yaml](../../data/phases.yaml).

## Where the project stands (2026-11-19)

**Phase 0 is complete** (2026-10-14). The server runs the stack under systemd, the control app answers over Tailscale, the public health page answers through the Cloudflare Tunnel, nightly backups reach the RAID and Google Drive, both Healthchecks.io checks are green, and the restore test passed.

**Phase 1 is complete.** The owner ran the acceptance test on 2026-10-18 and every item passed: the pricebook in the app matches the price matrix cell for cell, five random customers and every booked job check out against Baserow, and the restore test passes with real data. How the phase was run, step by step, is kept in the historical [Phase 1 runbook](../operations/phase-1-core-data-runbook.md). Phase 1 built:

- The data model for all nine areas, with change history ([../architecture/data-model.md](../architecture/data-model.md)).
- The pricebook load (`load_pricebook`), the pricing engine, time on site, the quote record and pricebook versioning ([../reference/pricing.md](../reference/pricing.md)).
- The Baserow and Setmore import (`import_baserow`), run as in [../operations/importing-baserow.md](../operations/importing-baserow.md); it can be run again with fresh exports until launch.
- The control app, installable on the Pixel and signed into over the tailnet address, with screens for customers and vehicles, the schedule and jobs, staff authorization and assignment, and the pricebook with drafts and publishing ([../reference/control-app.md](../reference/control-app.md)).

The returning-customer review queue, listed for Phase 1 in the first plan, moved to Phase 3 with quiet matching, because flags are raised only by website bookings. Phase 3 built it.

**Phase 2 is complete** (2026-10-29). The owner switched the catalog to the size-based vehicle classes and the new price book with `apply_size_classes` on 2026-10-28, worked through the booked-job review, the differences screen and the approval list, spot-checked every class in catalog search, and passed the backup and restore test the same day. How the phase was run, step by step, is kept in the historical [Phase 2 runbook](../operations/phase-2-vehicle-catalog-runbook.md). Phase 2 built, by pull request:

- **Step 1, the vehicle data import** (#33): `import_vehicle_data` loads the catalog from the EPA, NHTSA vPIC and the Canadian specifications, with each source's facts kept per model year ([../reference/vehicle-catalog.md](../reference/vehicle-catalog.md), decision 0071).
- **Step 2, classification** (#34, with the first dry run's fixes in #35): ordered rules and overrides give each model year a vehicle class and size variant, with a preview, a review queue and the `classify()` lookup the booking form will use; nameplates and one name per vehicle; Motorcycles are a vehicle class with Motorcycle Detail at $100 ([../reference/vehicle-classification.md](../reference/vehicle-classification.md), decisions 0072 to 0074).
- **Step 3, the catalog screens** (#36): lookup with a test price, model and vehicle overrides, the rules with a preview before each change applies, class settings, the review queue and each model's history, with the second dry run's fixes (decisions 0075 and 0076).
- **Step 4, customers' vehicles** (#37, with the first link dry run's fixes in #38): `link_vehicles` links customers' vehicles to the catalog without guessing, the differences screen settles each vehicle whose class differs, the two imported motorcycle jobs get their class and service, and the approval list holds the job history and a spot-check list (decisions 0077 to 0080).
- **Step 5, the monthly refresh** (#39, with deploy.sh enabling and checking every timer in #40): `dixie-vehicle-refresh.timer` refreshes the vehicle data on the first Sunday of each month, watched by Healthchecks.io, and never changes the class or size of a model with an override, an approval or customers' jobs without the owner (decision 0081).
- **The size-based vehicle classes** (the vehicle size report in #41, rules and dry run in #42, the switch in #43, and fixes from the apply dry runs in #44 to #46): cars, wagons, crossovers, SUVs, minivans and vans are classed by box volume into Small, Medium, Large, Full-size and Full-size Vans, pickups into Light Pickups and Full-size Trucks by a 760 cubic foot line, and `apply_size_classes` switched the catalog and published the new price book in one step (decisions 0082 to 0086).

**Phase 3 is complete** (2026-11-19). The owner booked test jobs on the Pixel through the staging site and each estimate matched his own math, approved the design, deleted the test records, and passed the backup and restore test with Phase 3's tables (122 of 122, plus the quote photos). How the phase was run, step by step, is kept in the historical [Phase 3 runbook](../operations/phase-3-scheduling-and-website-runbook.md). Phase 3 built, by pull request:

- **Step 0, the server incident follow-ups** (#48), and **Step 0b, backups that ride out a slow Google Drive** (#49, docs follow-up #50): the restore test never exits silently or leaves a restic lock, each new kernel is tested before it becomes the default, and the backup retries a slow Drive (decisions 0087 to 0089).
- **Step 1, addresses, sales tax and drive times** (#51, with #53 for addresses the Census geocoder can't match): verified addresses, the service area, Tennessee rates by boundary with a morning check, and traffic-aware drive times, with every Google call counted and capped ([../reference/sales-tax.md](../reference/sales-tax.md), decisions 0090 to 0092).
- **Step 2, scheduling settings and the availability check** (#54, follow-ups #55 and #56): the settings screen with change history, the one availability check, the manager override with its reason on the job, the schedule views and canceling a job (decisions 0093 to 0097).
- **Step 3, the Google Calendar sync** (#57): the Jobs calendar mirrored through a queue and the calendar worker, Time Off read into the availability check, and a nightly full check ([../reference/scheduling-and-calendars.md](../reference/scheduling-and-calendars.md), decision 0098).
- **Step 4, the public API** (#58): services and prices, vehicle lookup, addresses, quotes, open times, bookings, quote requests with photos and offline requests ([../reference/public-api.md](../reference/public-api.md), decisions 0099 and 0100).
- **Step 5, website bookings in the control app** (#59, follow-up #60): quiet matching with its review queue, staff assignment, and screens for quote requests, offline requests and second vehicles (decisions 0101 and 0102).
- **Step 6, the website on staging** (service levels for interior work in #61, the site inputs in #63, the site in #65, follow-ups #66 and #67, the faster homepage in #69): the Astro site with every current address, the booking flow with its estimate card, quote requests with photos, and the request a time form Cloudflare holds while the server can't be reached ([../reference/website-and-seo.md](../reference/website-and-seo.md), [../reference/booking-flow.md](../reference/booking-flow.md), decisions 0103 and 0105).
- **Step 7, the changes from acceptance testing** (A in #68, B in #70, C in #71, D in #72): add-on rules, the default staff, one text consent, the website's wording and layout, the Service Area map, reviews kept in the control app, unavailable days grayed out and one website payment list (decisions 0106 to 0110).
- Side tasks: cloudflared pinned (#52), CI pinned to Ubuntu 24.04 (#62), and the vehicle class pictures left out of the portfolio copy (#64, decision 0104).

The class photo cards carried over from Phase 2 show their pictures. The possible future vehicle classes in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml) (Oversized Vans & Trucks, RVs priced by the foot, Boats by quote) are still not built; any class set to be booked by quote uses the quote request form with no new code.

**Phase 4, texts, alerts and payments, is next.** Customers keep booking through Setmore until the Phase 5 launch.

Phase 1 started with two carry-overs from Phase 0, both done: `DEPLOY_REMOTE` and `DEPLOY_BRANCH` are in the server's `.env` and `ops/deploy.sh` works (confirmed by the owner 2026-10-17; the deploy key secret was renamed from `DEPLOY_KEY` to `DEPLOY_SSH_KEY` on 2026-10-13), and the restore test passed on 2026-10-14. Two more were done in the documentation migration on 2026-10-13: `BWS_SERVER_URL` is in `.env.example` and every script that calls `bws` uses it, and the secret names in `.env.example` and [data/configuration.yaml](../../data/configuration.yaml) match what the scripts fetch.

## Owner actions still open

Answers and checks only the owner can give, including those carried over from Phases 1 to 3. The list is kept in [data/phases.yaml](../../data/phases.yaml) under `owner_actions_open`.

| Needed before | Action |
| --- | --- |
| The booked job on 2026-11-28 | Attach the vehicle to the job when the customer says what it is, then settle its price on the booked-job review |
| Each vehicle's next visit | Confirm the year of each customer vehicle flagged "year needed", which took its model's newest generation's class (decision 0083) |
| Phase 4, start now | Register with the carriers through Quo, using the answers in [text-messages.md](../reference/text-messages.md) (one consent checkbox, no promotional texts). The reviewers must see the consent checkbox at the address given, which is the staging site until launch |
| Phase 4, by 2027-01-15 | The Google Cloud free trial ends about 2027-02-03. Upgrade the account by 2027-01-15 and set the daily quota caps the same day: each free monthly amount divided by 31, so 322 Places autocomplete, 322 Place Details Essentials and 161 Routes. If the trial ends first, the Maps calls stop |
| Phase 4 | Switch the off-site backup's rclone remote to the business's own Google OAuth client, following [backups-and-restore.md](../operations/backups-and-restore.md#switching-drive-to-the-businesss-own-google-client). Drive's rate-limit errors on rclone's shared client continue, though the retries still succeed |
| Phase 4 | Confirm the Stripe account is in the business's name and run a small Tap to Pay test; confirm the Venmo and Cash App accounts are business profiles ([payments.md](../reference/payments.md)) |
| Ongoing | Keep the server on the pinned kernel until a newer one passes the test in [updating-the-kernel.md](../operations/updating-the-kernel.md). Filing the Launchpad bug is optional |
| Before Phase 5 | Ask the accountant about Georgia sales and income tax for the out-of-area customer (decision 0037), and how Tennessee sources sales tax for a mobile service ([sales-tax.md](../reference/sales-tax.md)) |
| Before Phase 5 | Confirm the licenses of the five service page photos, believed to be royalty-free stock. The vehicle class pictures are renders the business holds no license for (the owner's decision, [decision 0104](../decisions/0104-portfolio-copy-leaves-out-unlicensed-pictures.md)); the original SVG drawings are kept outside the repository as a swap |
| Phase 5 | The new Privacy Policy and Text Message Terms take the effective date of the day the new site goes live. The WordPress pages stay as they are until the cutover |
| Always | Reviews live only in the control app's Reviews screen ([decision 0109](../decisions/0109-reviews-kept-in-the-control-app.md)). They never go in data files, fixtures or the portfolio copy |

## Where the plan review of 2026-10-17 lands

Before Phase 1 Step 3 the owner reviewed the plan and agreed ten changes, recorded as decisions 0056 to 0062 in the [decision index](../decisions/README.md). Each lands in the phase that builds it; the Phase 1 to 3 ones are built:

| Where | What |
| --- | --- |
| Phase 1 Step 3 | Service hours without setup and breakdown in the pricebook load, the quote record, time on site, and room in the pricing engine for another price basis (built) |
| Phase 1 Step 5b | Staff authorization per service, its two screens, and assigning staff from the qualified list (built) |
| Phase 2 | Vehicle classification rules as data, with overrides, a preview and vehicle class settings (built) |
| Phase 3 | The scheduling settings screen, the availability check, the calendar sync and conflict rules, and staff assignment for website bookings (the default staff, decision 0107) (built) |
| Phase 4 | Arrival and departure taps |

## The phases

| Phase | What gets built | Done when | Status |
| --- | --- | --- | --- |
| 0. Foundations | Accounts, the server stack (Docker, PostgreSQL, Caddy, tunnel), Tailscale access, backups, monitoring, the repository | A backup has been restored successfully and the server answers through the tunnel | Done (2026-10-14) |
| 1. Core data and control app | The data model for all nine areas; screens for customers, vehicles, pricebook, appointments and staff; the Baserow import; pricebook versioning | The pricebook in the app matches the price matrix cell for cell, and the imported history is searchable | Done (2026-10-18) |
| 2. Vehicle catalog | EPA and NHTSA import (with vPIC's Canadian specifications), owner-editable classification rules with a preview, overrides, vehicle class settings, size-variant flags, review queue, monthly refresh | The owner approves the class for every model in the job history and a spot-check list | Done (2026-10-29) |
| 3. Scheduling and website | Scheduling settings screen, the availability check, Google Calendar sync and conflict rules, staff assignment for website bookings, sales tax, booking API, quiet customer matching with its review queue (moved from Phase 1), the Astro site with the estimate card on a staging address (carrier registration, planned here, starts now and is carried into Phase 4) | The owner completes test bookings on the phone, estimates match the owner's own math, and the design is approved | Done (2026-11-19) |
| 4. Texts, alerts and payments | Quo messages, STOP and HELP handling, time-to-leave alerts, arrival and departure taps, Stripe links and Tap to Pay matching, "paid" buttons, invoices and receipts | One test appointment runs from booking through reminder, payment by every method and review request | Next |
| 5. Launch | Redirects from WordPress, DNS cutover, Search Console check, number port, Setmore retired | Old links redirect, a real customer books, and Setmore is switched off | Planned |
| 6. Back office | GnuCash export, sales tax reports, promotions, marketing campaigns, staff records and pay | A month's export imports cleanly into GnuCash and matches the bank deposits | Planned |
| 7. Bitcoin | BTCPay Server, the Lightning decision, automatic Bitcoin invoices, a GnuCash bitcoin account | A test Bitcoin invoice marks its appointment paid | Planned |

## Why the database covers everything from Phase 1

The data model is designed for all nine business areas in Phase 1 (customers, appointments, pricebook, billing, history, promotions, staff, bookkeeping, marketing), so later phases add screens without restructuring stored data. See [../architecture/data-model.md](../architecture/data-model.md).

## Fixed waits outside the project's control

Carrier registration for automated texts takes from a day to several weeks, and it can start now that the booking form with its consent checkbox is on the staging site. Phase 4's automated texts and the port of the business number wait for that approval. See [../reference/text-messages.md](../reference/text-messages.md).

## Later add-ons, not scheduled

- **Automatic arrival and departure.** A small native Android companion app using Android geofencing to record arrival and departure without a tap, installed directly rather than from the Play Store. See [decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md).
