---
title: Roadmap and phase status
summary: The eight build phases, what each delivers, the test that ends it, and where the project stands now.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-14
tags: [roadmap, phases, status]
related: [data/phases.yaml, docs/operations/phase-0-foundations-runbook.md]
---

# Roadmap and phase status

The booking path ships first because it earns money; the back-office features follow once real data is flowing. Each phase becomes a GitHub milestone, and each task an issue. A phase ends when the owner runs its test and it passes. The structured list is in [data/phases.yaml](../../data/phases.yaml).

## Where the project stands (2026-10-13)

**Phase 0 is complete**, except for one deferred check. The server runs the empty stack under systemd, the control app answers over Tailscale, the public health page answers through the Cloudflare Tunnel, nightly backups reach the RAID and Google Drive, and both Healthchecks.io checks are green.

The **restore test is deferred**: it fails correctly because the database has no tables yet. It will pass once Phase 1 runs the first migrations.

**Phase 1 is next.** It starts with these carry-overs from Phase 0:

1. Add `DEPLOY_REMOTE` and `DEPLOY_BRANCH` to the server's `.env` before the first run of `ops/deploy.sh`. (The deploy key secret was renamed from `DEPLOY_KEY` to `DEPLOY_SSH_KEY`, the name `ops/deploy.sh` asks for, on 2026-10-13.)
2. Once the first models exist, run `sudo ops/restore-test.sh` and confirm it passes, which closes Phase 0.

Two other carry-overs were done in the documentation migration on 2026-10-13: `BWS_SERVER_URL` is in `.env.example` and every script that calls `bws` uses it, and the secret names in `.env.example` and [data/configuration.yaml](../../data/configuration.yaml) match what the scripts fetch.

## The phases

| Phase | What gets built | Done when | Status |
| --- | --- | --- | --- |
| 0. Foundations | Accounts, the server stack (Docker, PostgreSQL, Caddy, tunnel), Tailscale access, backups, monitoring, the repository | A backup has been restored successfully and the server answers through the tunnel | Done, restore test deferred |
| 1. Core data and control app | The data model for all nine areas; screens for customers, vehicles, pricebook and appointments; the Baserow import; pricebook versioning; the returning-customer review queue | The pricebook in the app matches the price matrix cell for cell, and the imported history is searchable | Next |
| 2. Vehicle catalog | EPA and NHTSA import, class rules, size-variant flags, review queue, monthly refresh | The owner approves the class for every model in the job history and a spot-check list | Planned |
| 3. Scheduling and website | Availability engine, Google Calendar sync, sales tax, booking API, quiet customer matching, the Astro site with the estimate card on a staging address, carrier registration once the booking form is public | The owner completes test bookings on the phone, estimates match the owner's own math, and the design is approved | Planned |
| 4. Texts, alerts and payments | Quo messages, STOP and HELP handling, time-to-leave alerts, Stripe links and Tap to Pay matching, "paid" buttons, invoices and receipts | One test appointment runs from booking through reminder, payment by every method and review request | Planned |
| 5. Launch | Redirects from WordPress, DNS cutover, Search Console check, number port, Setmore retired | Old links redirect, a real customer books, and Setmore is switched off | Planned |
| 6. Back office | GnuCash export, sales tax reports, promotions, marketing campaigns, staff records and pay | A month's export imports cleanly into GnuCash and matches the bank deposits | Planned |
| 7. Bitcoin | BTCPay Server, the Lightning decision, automatic Bitcoin invoices, a GnuCash bitcoin account | A test Bitcoin invoice marks its appointment paid | Planned |

## Why the database covers everything from Phase 1

The data model is designed for all nine business areas in Phase 1 (customers, appointments, pricebook, billing, history, promotions, staff, bookkeeping, marketing), so later phases add screens without restructuring stored data. See [../architecture/data-model.md](../architecture/data-model.md).

## Fixed waits outside the project's control

Carrier registration for automated texts takes from a day to several weeks, and it cannot start until the new booking form with its consent checkboxes is public in Phase 3. Porting the business number waits for that approval. See [../reference/text-messages.md](../reference/text-messages.md).
