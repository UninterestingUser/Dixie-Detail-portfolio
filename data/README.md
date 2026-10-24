---
title: Data files
summary: What each structured data file in data/ holds, which are seeds for the database, and how they relate to the documentation.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-24
---

# Data files

Structured facts live here so that code and people read the same numbers. Each YAML file starts with a `meta` block naming the doc that explains it. Rules for editing are in [../docs/CONVENTIONS.md](../docs/CONVENTIONS.md).

| File | Holds | Role |
| --- | --- | --- |
| [price-matrix.csv](price-matrix.csv) | The 90 prices and one-person service hours (setup and breakdown not included) | Seed for the pricebook (Phase 1); the only price source |
| [services.yaml](services.yaml) | The service catalog | Seed and reference |
| [pricing-rules.yaml](pricing-rules.yaml) | Condition levels, maintenance ratios, service time, crew time, rounding, full-day flag, the quote | Seed for pricebook settings |
| [vehicle-classes.yaml](vehicle-classes.yaml) | The seven vehicle classes, their size variants and settings, the launch classification rules and model overrides, and the possible future classes | Read by `load_pricebook` (classes) and kept in step by `classify_vehicles` (launch rules and overrides the owner has not edited) |
| [vehicle-names.yaml](vehicle-names.yaml) | The names customers know: EPA base models split into nameplates, the other spellings of one vehicle, make spellings, customers' names for vehicles filed under another name or make (some for certain years), and the trim words left off a customer's model name | Read by `import_vehicle_data`, `classify_vehicles`, `link_vehicles` and the booking lookup |
| [approval-spot-checks.yaml](approval-spot-checks.yaml) | The models near a class boundary the owner approves on the approval list, with why each is there | Read by the control app's approval list |
| [third-row-seating.yaml](third-row-seating.yaml) | Which crossovers and midsize SUVs since 2010 have a third row always, optionally or never, by model year, checked by the owner | Read by `classify_vehicles` on every run |
| [booking-rules.yaml](booking-rules.yaml) | Launch values of the scheduling settings: open days, hours, start times, notice, setup and breakdown, capacity, gaps, calendar sync timing, alert timing | Seed for scheduling settings |
| [vehicle-data-import.yaml](vehicle-data-import.yaml) | The truck, van and motorcycle makes the vehicle data import asks vPIC for (with the makes that sell only motorcycles), the model years, the pacing, and Canadian make names | Read by `import_vehicle_data` and `link_vehicles` |
| [service-area.yaml](service-area.yaml) | Counties, out-of-area policy, tax sourcing | Seed and reference |
| [configuration.yaml](configuration.yaml) | Every setting and secret name | Reference; kept in step with `.env.example` |
| [integrations.yaml](integrations.yaml) | Outside services and their status | Reference |
| [gnucash-accounts.yaml](gnucash-accounts.yaml) | GnuCash account mapping | Seed for the export (Phase 6) |
| [message-templates.yaml](message-templates.yaml) | Text message wording and consent | Seed for templates (Phase 4) |
| [business.yaml](business.yaml) | Contact details, brand, profiles | Reference |
| [phases.yaml](phases.yaml) | Build phases and status | Reference |

## Seeds and the database

PostgreSQL is the single source of truth once a feature is built. Files marked "seed" load the launch defaults; after that, the owner changes values in the control app. When a default changes, update the file in the same pull request so the documentation stays true. A later phase can add a scheduled export that rewrites these files from the database, so an AI reading them always sees live values.
