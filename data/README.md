---
title: Data files
summary: What each structured data file in data/ holds, which are seeds for the database, and how they relate to the documentation.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-13
---

# Data files

Structured facts live here so that code and people read the same numbers. Each YAML file starts with a `meta` block naming the doc that explains it. Rules for editing are in [../docs/CONVENTIONS.md](../docs/CONVENTIONS.md).

| File | Holds | Role |
| --- | --- | --- |
| [price-matrix.csv](price-matrix.csv) | The 90 prices and one-person hours | Seed for the pricebook (Phase 1); the only price source |
| [services.yaml](services.yaml) | The service catalogue | Seed and reference |
| [pricing-rules.yaml](pricing-rules.yaml) | Condition levels, maintenance ratios, crew time, rounding, full-day flag | Seed for pricebook settings |
| [vehicle-classes.yaml](vehicle-classes.yaml) | The six vehicle classes and size variants | Seed and reference |
| [booking-rules.yaml](booking-rules.yaml) | Working days, notice, arrival times, capacity, alert timing | Seed for scheduling settings |
| [service-area.yaml](service-area.yaml) | Counties, out-of-area policy, tax sourcing | Seed and reference |
| [configuration.yaml](configuration.yaml) | Every setting and secret name | Reference; kept in step with `.env.example` |
| [integrations.yaml](integrations.yaml) | Outside services and their status | Reference |
| [gnucash-accounts.yaml](gnucash-accounts.yaml) | GnuCash account mapping | Seed for the export (Phase 6) |
| [message-templates.yaml](message-templates.yaml) | Text message wording and consent | Seed for templates (Phase 4) |
| [business.yaml](business.yaml) | Contact details, brand, profiles | Reference |
| [phases.yaml](phases.yaml) | Build phases and status | Reference |

## Seeds and the database

PostgreSQL is the single source of truth once a feature is built. Files marked "seed" load the launch defaults; after that, the owner changes values in the control app. When a default changes, update the file in the same pull request so the documentation stays true. A later phase can add a scheduled export that rewrites these files from the database, so an AI reading them always sees live values.
