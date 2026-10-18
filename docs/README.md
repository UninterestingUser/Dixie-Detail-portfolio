---
title: Dixie Detail documentation
summary: The starting point for all documentation about the Dixie Detail business system, with a map of every document and how to use them.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-17
tags: [index, documentation]
related: [docs/CONVENTIONS.md, data/README.md, llms.txt]
---

# Dixie Detail documentation

This folder explains the Dixie Detail business system: why it exists, how it is built, the business rules it follows, every decision behind it, and how to run it. It is written for the owner, future staff, developers and AI assistants alike.

**Where things stand (2026-10-14):** Phase 0 (Foundations) is complete; its restore test passed on 2026-10-14. Phase 1 (Core data and control app) is under way, with the data model built. See [overview/roadmap.md](overview/roadmap.md).

## Start here

- New to the project: [overview/project-goals.md](overview/project-goals.md), then [architecture/system-overview.md](architecture/system-overview.md).
- Looking up a rule: the reference section below, and the [glossary](overview/glossary.md) for terms.
- Wondering why something is the way it is: [decisions/README.md](decisions/README.md).
- Fixing something on the server: [operations/troubleshooting.md](operations/troubleshooting.md).
- Writing or changing docs: [CONVENTIONS.md](CONVENTIONS.md).

## How to read the labels

Every page starts with a header block. `status` matters most: **current** describes something that exists today, **planned** describes a design not built yet, and **historical** is a record kept for context. `visibility: restricted` marks infrastructure and security pages meant for the owner and developers only.

## Overview: why the system exists and the vocabulary

| Document | Summary | Status |
| --- | --- | --- |
| [Business profile](overview/business-profile.md) | Who Dixie Detail is, what it sells, where it works, how it is staffed and paid, and which tools it uses today. | current |
| [Glossary](overview/glossary.md) | The exact meaning of every business and technical term used in the Dixie Detail documentation, so people and AI use each word one way. | current |
| [Project goals and scope](overview/project-goals.md) | Why the Dixie Detail business system is being built, what it must achieve, what it deliberately leaves out, and how success is judged. | current |
| [Roadmap and phase status](overview/roadmap.md) | The eight build phases, what each delivers, the test that ends it, and where the project stands now. | current |
| [Running costs](overview/running-costs.md) | What the finished system costs to run each month, item by item, with the date each figure was checked. | current |

## Architecture: how it is built

| Document | Summary | Status |
| --- | --- | --- |
| [Backups and monitoring design](architecture/backups-and-monitoring.md) | How the database is backed up every night to the RAID and to Google Drive, how long copies are kept, and how Healthchecks.io watches the backups and the public path. | current |
| [Data model](architecture/data-model.md) | The records the database holds across all nine business areas, as built in Phase 1, with a diagram of the main records and what each one is for. | current |
| [Outside services and integrations](architecture/integrations.md) | Every outside service the system uses or will use, what it does for the business, which phase connects it, and how it talks to the core app. | current |
| [Network and access](architecture/network-and-access.md) | How staff reach the private control app over Tailscale, how the public reaches only the health page and booking API through the Cloudflare Tunnel, and which host names the app accepts. | current |
| [Secrets architecture](architecture/secrets.md) | How every key, password and token is kept in Bitwarden Secrets Manager, how the server holds one encrypted token, and how secrets reach containers without touching disk. | current |
| [Server and Docker stack](architecture/server-and-stack.md) | The home server's hardware and folders, the four containers of the Phase 0 stack, and the systemd units and scripts that start, back up and watch it. | current |
| [System overview](architecture/system-overview.md) | The parts of the Dixie Detail business system, how they connect, how data moves between them, and the principles every part follows. | current |

## Reference: business rules and behaviour

| Document | Summary | Status |
| --- | --- | --- |
| [Customer booking flow](reference/booking-flow.md) | The seven steps a customer follows on the website to book a job, how the running estimate card behaves, and how address and phone entry are validated. | planned |
| [Bookkeeping with GnuCash](reference/bookkeeping-gnucash.md) | How paid jobs, fees, payouts and refunds become balanced GnuCash transactions, which accounts each event posts to, and the CSV layout the owner imports. | current |
| [Settings and secrets reference](reference/configuration.md) | How the system's configuration is split between non-secret settings in .env and secrets in Bitwarden, with rules for adding or renaming either. | current |
| [Control app](reference/control-app.md) | The private web app the owner and staff use to run the business, the areas it will contain, and the rules it follows. | planned |
| [Moving existing records](reference/data-migration.md) | How customers, vehicles and appointments are imported once from Baserow, with Setmore filling gaps, before both are retired. | planned |
| [Payments](reference/payments.md) | How each payment method is taken at the job and marked paid, and the payment rules that apply to every appointment. | current |
| [When prices or services change](reference/pricebook-changes.md) | How pricebook edits are published as versions with an effective date, why completed jobs never change, and how the owner decides case by case for booked jobs. | current |
| [Pricing rules](reference/pricing.md) | How every price is built from the price matrix, what size variants mean for each vehicle class, how condition and crew size change price and time, and why the quoted price is the price of record. | current |
| [Returning customers and quiet matching](reference/returning-customers.md) | How a new booking is linked to an existing customer by mobile number without showing the customer anything, and how the owner resolves differences in the control app. | current |
| [Sales tax](reference/sales-tax.md) | How sales tax is added at the rate for the customer's service address, how the rate is found and kept current, how approved out-of-area addresses are treated, and how collected tax is tracked until remitted. | current |
| [Scheduling, calendars and time-to-leave alerts](reference/scheduling-and-calendars.md) | The scheduling settings and the one availability check that decide which days and start times are open, time on site, the calendar sync and conflict rules, time-to-leave alerts and arrival taps. | current |
| [Text messages and consent](reference/text-messages.md) | Which automated texts the system sends, the two kinds of consent each one needs, the exact consent wording, automatic STOP and HELP replies, and the carrier registration plan. | current |
| [Vehicle classification](reference/vehicle-classification.md) | How a customer's year, make and model will be turned into a vehicle class and size variant, using free EPA and NHTSA data, owner-editable classification rules, overrides and a review queue. | planned |
| [Website and SEO](reference/website-and-seo.md) | The structure, design direction and search-ranking safeguards for the new Astro website that replaces WordPress at launch. | planned |

## Operations: running the server

| Document | Summary | Status |
| --- | --- | --- |
| [Running and checking backups, and restoring](operations/backups-and-restore.md) | How to confirm the nightly backup ran, run one by hand, test a restore, and recover the database from the RAID or from Google Drive. | current |
| [Deploying changes to the server](operations/deploying-changes.md) | The routine for getting a merged pull request onto the server, and what to restart, copy or add afterwards depending on what changed. | current |
| [Monitoring and alerts](operations/monitoring.md) | What the two Healthchecks.io checks watch, what to do when an alert email arrives, and how to test the alerts. | current |
| [Phase 0 foundations runbook](operations/phase-0-foundations-runbook.md) | The step-by-step procedure that built the server foundation in Phase 0, with every correction found along the way, usable to rebuild the server from scratch. | current |
| [Managing secrets](operations/secrets-management.md) | Step-by-step procedures for adding, renaming and rotating secrets, re-encrypting the server's Bitwarden token, and replacing the deploy key. | current |
| [Publishing the public portfolio copy](operations/publishing-the-portfolio.md) | How the owner publishes and updates the public copy of this private repository, with every commit rewritten to hide server addresses and private details, and what to do when the publish script stops. | current |
| [Troubleshooting](operations/troubleshooting.md) | Known problems with the server, stack, backups and tools, each with the exact symptom, the cause and the fix, collected from Phase 0 onward. | current |
| [Workstation setup](operations/workstation-setup.md) | How the owner's Fedora workstation is set up to work on the repository with Git, the GitHub CLI and Claude Code, without storing secrets in plaintext. | current |

## Guides: day-to-day use

| Document | Summary | Status |
| --- | --- | --- |
| [Guides for day-to-day use](guides/README.md) | The index of task-based guides for using the Dixie Detail system day to day, by role, with the guides planned for each phase. | planned |

## Decisions

Every decision has its own record in [decisions/](decisions/README.md): 64 records as of 2026-10-17, from the choice of PostgreSQL and Django to the documentation rules themselves.

## Structured data

Hard facts (prices, rules with numbers, settings and secret names, accounts, message wording) are in [../data/](../data/README.md) as YAML, plus the price matrix as CSV.

## Sources migrated into this folder

On 2026-10-13 these were migrated into the repository and frozen at their original locations:

- The Claude doc "Dixie Detail Business System: Executive Plan" (2026-10-07 to 2026-10-13)
- The Claude doc "Phase 0: Foundations runbook" (2026-10-12 to 2026-10-13)
- The Claude doc "Dixie Detail: Privacy Policy, Text Terms and Quo Registration Answers" (2026-10-07); the consent wording and replies are in [reference/text-messages.md](reference/text-messages.md), and the published policy pages remain the authority for their own text
- The earlier repository docs (`docs/architecture.md`, `docs/pricing.md`, `docs/scheduling.md`, `docs/integrations.md`, `docs/compliance.md`, `docs/roadmap.md`, `docs/decisions.md`, `docs/setup/server.md`), and the Phase 0 setup notes written with the code (`docs/setup/stack.md`, `docs/setup/backups.md`)

Customer-specific import corrections from the executive plan were deliberately not migrated, because they are personal data.
