---
title: Roadmap and phase status
summary: The eight build phases, what each delivers, the test that ends it, and where the project stands now.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-18
tags: [roadmap, phases, status]
related: [data/phases.yaml, docs/operations/phase-0-foundations-runbook.md, docs/operations/phase-1-core-data-runbook.md, docs/decisions/README.md]
---

# Roadmap and phase status

The booking path ships first because it earns money; the back-office features follow once real data is flowing. Each phase becomes a GitHub milestone, and each task an issue. A phase ends when the owner runs its test and it passes. The structured list is in [data/phases.yaml](../../data/phases.yaml).

## Where the project stands (2026-10-18)

**Phase 0 is complete** (2026-10-14). The server runs the stack under systemd, the control app answers over Tailscale, the public health page answers through the Cloudflare Tunnel, nightly backups reach the RAID and Google Drive, both Healthchecks.io checks are green, and the restore test passed.

**Phase 1 is complete.** The owner ran the acceptance test on 2026-10-18 and every item passed: the pricebook in the app matches the price matrix cell for cell, five random customers and every booked job check out against Baserow, and the restore test passes with real data. How the phase was run, step by step, is kept in the historical [Phase 1 runbook](../operations/phase-1-core-data-runbook.md). Phase 1 built:

- The data model for all nine areas, with change history ([../architecture/data-model.md](../architecture/data-model.md)).
- The pricebook load (`load_pricebook`), the pricing engine, time on site, the quote record and pricebook versioning ([../reference/pricing.md](../reference/pricing.md)).
- The Baserow and Setmore import (`import_baserow`), run as in [../operations/importing-baserow.md](../operations/importing-baserow.md); it can be run again with fresh exports until launch.
- The control app, installable on the Pixel and signed into over the tailnet address, with screens for customers and vehicles, the schedule and jobs, staff authorization and assignment, and the pricebook with drafts and publishing ([../reference/control-app.md](../reference/control-app.md)).

The returning-customer review queue, listed for Phase 1 in the first plan, moved to Phase 3 with quiet matching: flags are raised only by website bookings, which start in Phase 3. The data model already holds them.

**Phase 2, the vehicle catalog, is next.**

Phase 1 started with two carry-overs from Phase 0, both done: `DEPLOY_REMOTE` and `DEPLOY_BRANCH` are in the server's `.env` and `ops/deploy.sh` works (confirmed by the owner 2026-10-17; the deploy key secret was renamed from `DEPLOY_KEY` to `DEPLOY_SSH_KEY` on 2026-10-13), and the restore test passed on 2026-10-14. Two more were done in the documentation migration on 2026-10-13: `BWS_SERVER_URL` is in `.env.example` and every script that calls `bws` uses it, and the secret names in `.env.example` and [data/configuration.yaml](../../data/configuration.yaml) match what the scripts fetch.

## Owner actions still open

Answers and checks only the owner can give, including those carried over from Phase 1. None blocks Phase 2. The list is kept in [data/phases.yaml](../../data/phases.yaml) under `owner_actions_open`.

| Needed before | Action |
| --- | --- |
| Phase 2's classification rules are settled | Decide whether to change how vehicles are priced, with a factor beyond vehicle class, size variant and condition. It is cheapest to settle before the booking flow is built |
| Phase 3 | Confirm or drop the quarter-hour rounding of a second Monthly job's start (decisions 0022 and 0056) |
| Phase 3 | Ask the accountant about Georgia sales tax for the out-of-area customer, and whether Georgia work creates a Georgia income tax filing (decision 0037, [sales-tax.md](../reference/sales-tax.md)) |
| Phase 3 | Write short descriptions, in the owner's own words, of each service and condition level for the website |
| Phase 3 | Collect the Google Business Profile link for the website footer ([data/business.yaml](../../data/business.yaml)) |
| Phase 4 | Confirm the Stripe account is in the business's name and run a small Tap to Pay test; confirm the Venmo and Cash App accounts are business profiles ([payments.md](../reference/payments.md)) |

## Where the plan review of 2026-10-17 lands

Before Phase 1 Step 3 the owner reviewed the plan and agreed ten changes, recorded as decisions 0056 to 0062 in the [decision index](../decisions/README.md). Each lands in the phase that builds it; the Phase 1 ones are built:

| Where | What |
| --- | --- |
| Phase 1 Step 3 | Service hours without setup and breakdown in the pricebook load, the quote record, time on site, and room in the pricing engine for another price basis (built) |
| Phase 1 Step 5b | Staff authorization per service, its two screens, and assigning staff from the qualified list (built) |
| Phase 2 | Vehicle classification rules as data, with overrides, a preview and vehicle class settings |
| Phase 3 | The scheduling settings screen, the availability check, the calendar sync and conflict rules, and the assign-staff prompt for website bookings |
| Phase 4 | Arrival and departure taps |

## The phases

| Phase | What gets built | Done when | Status |
| --- | --- | --- | --- |
| 0. Foundations | Accounts, the server stack (Docker, PostgreSQL, Caddy, tunnel), Tailscale access, backups, monitoring, the repository | A backup has been restored successfully and the server answers through the tunnel | Done (2026-10-14) |
| 1. Core data and control app | The data model for all nine areas; screens for customers, vehicles, pricebook, appointments and staff; the Baserow import; pricebook versioning | The pricebook in the app matches the price matrix cell for cell, and the imported history is searchable | Done (2026-10-18) |
| 2. Vehicle catalog | EPA and NHTSA import (with vPIC's Canadian specifications), owner-editable classification rules with a preview, overrides, vehicle class settings, size-variant flags, review queue, monthly refresh | The owner approves the class for every model in the job history and a spot-check list | Next |
| 3. Scheduling and website | Scheduling settings screen, the availability check, Google Calendar sync and conflict rules, the assign-staff prompt for website bookings, sales tax, booking API, quiet customer matching with its review queue (moved from Phase 1), the Astro site with the estimate card on a staging address, carrier registration once the booking form is public | The owner completes test bookings on the phone, estimates match the owner's own math, and the design is approved | Planned |
| 4. Texts, alerts and payments | Quo messages, STOP and HELP handling, time-to-leave alerts, arrival and departure taps, Stripe links and Tap to Pay matching, "paid" buttons, invoices and receipts | One test appointment runs from booking through reminder, payment by every method and review request | Planned |
| 5. Launch | Redirects from WordPress, DNS cutover, Search Console check, number port, Setmore retired | Old links redirect, a real customer books, and Setmore is switched off | Planned |
| 6. Back office | GnuCash export, sales tax reports, promotions, marketing campaigns, staff records and pay | A month's export imports cleanly into GnuCash and matches the bank deposits | Planned |
| 7. Bitcoin | BTCPay Server, the Lightning decision, automatic Bitcoin invoices, a GnuCash bitcoin account | A test Bitcoin invoice marks its appointment paid | Planned |

## Why the database covers everything from Phase 1

The data model is designed for all nine business areas in Phase 1 (customers, appointments, pricebook, billing, history, promotions, staff, bookkeeping, marketing), so later phases add screens without restructuring stored data. See [../architecture/data-model.md](../architecture/data-model.md).

## Fixed waits outside the project's control

Carrier registration for automated texts takes from a day to several weeks, and it cannot start until the new booking form with its consent checkboxes is public in Phase 3. Porting the business number waits for that approval. See [../reference/text-messages.md](../reference/text-messages.md).

## Later add-ons, not scheduled

- **Automatic arrival and departure.** A small native Android companion app using Android geofencing to record arrival and departure without a tap, installed directly rather than from the Play Store. See [decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md).
