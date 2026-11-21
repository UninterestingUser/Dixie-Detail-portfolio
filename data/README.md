---
title: Data files
summary: What each structured data file in data/ holds, which are seeds for the database, and how they relate to the documentation.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-21
---

# Data files

Structured facts live here so that code and people read the same numbers. Each YAML file starts with a `meta` block naming the doc that explains it. Rules for editing are in [../docs/CONVENTIONS.md](../docs/CONVENTIONS.md).

| File | Holds | Role |
| --- | --- | --- |
| [price-matrix.csv](price-matrix.csv) | The 91 prices and one-person service hours (setup and breakdown not included) for the size-based vehicle classes | Loaded by `load_pricebook`, after the price book check, as version 1 or a new draft; the only price source |
| [services.yaml](services.yaml) | The service catalog, with which services take a condition level (`condition_applies`) and the services each add-on goes with (`goes_with`) | Seed and reference; `condition_applies` and `goes_with` are loaded with each pricebook version |
| [pricing-rules.yaml](pricing-rules.yaml) | Condition levels (which services take one, Level 3 booked by quote), maintenance ratios, service time, crew time, rounding, full-day flag, the quote | Loaded by `load_pricebook` with each version; a difference makes a new draft |
| [vehicle-classes.yaml](vehicle-classes.yaml) | The eight size-based vehicle classes, their size variants, settings and photo cards, the retired body-type classes, the rule settings, and the possible future classes | Read by `load_pricebook` (classes) and `classify_vehicles` (rule settings) |
| [site-content.yaml](site-content.yaml) | The website's text in the owner's words: the four service cards and services page sections (with the old pages they redirect from), each service's text and the classes a service is only for (`only_for`), the red box headings, the condition level cards and quote notes, the homepage services subhead and the services page's top, and the picture for each vehicle class and section | Read by the Astro site in `site/` at build time; `old_pages` also makes `_redirects` |
| [site-pages.yaml](site-pages.yaml) | Each website page's address, title and description, and the text carried over from the current site, with the owner's later changes: how it works, the counties, the homepage's map and six questions, every question, the about page and the city pages | Read by the Astro site in `site/` at build time |
| [vehicle-names.yaml](vehicle-names.yaml) | The names customers know: EPA base models split into nameplates, the other spellings of one vehicle, make spellings, customers' names for vehicles filed under another name or make (some for certain years), and the trim words left off a customer's model name | Read by `import_vehicle_data`, `classify_vehicles`, `link_vehicles` and the booking lookup |
| [approval-spot-checks.yaml](approval-spot-checks.yaml) | The models the owner spot-checks on the approval list, some for certain model years | Read by the control app's approval list |
| [size-classes.yaml](size-classes.yaml) | The size-based classification rules (decisions 0082 and 0083): the box-volume lines, the pickup line, smoothing, the vans, the rules in order, the model overrides, seat rows, and the proposed classes for vehicles left in a retired class | Kept in step by `classify_vehicles` (launch rules and overrides the owner has not edited); read by `apply_size_classes` |
| [third-row-seating.yaml](third-row-seating.yaml) | Which crossovers and midsize SUVs since 2010 have a third row always, optionally or never, by model year, checked by the owner | Read by `classify_vehicles` on every run |
| [booking-rules.yaml](booking-rules.yaml) | Launch values of the scheduling settings: open days, hours, start times, notice, setup and breakdown, capacity, gaps, calendar sync timing, alert timing | Seed for scheduling settings |
| [vehicle-data-import.yaml](vehicle-data-import.yaml) | The truck, van and motorcycle makes the vehicle data import asks vPIC for (with the makes that sell only motorcycles), the model years, the pacing, and Canadian make names | Read by `import_vehicle_data` and `link_vehicles` |
| [service-area.yaml](service-area.yaml) | Counties, out-of-area policy, tax sourcing | Seed and reference |
| [configuration.yaml](configuration.yaml) | Every setting and secret name | Reference; kept in step with `.env.example` |
| [integrations.yaml](integrations.yaml) | Outside services and their status | Reference |
| [gnucash-accounts.yaml](gnucash-accounts.yaml) | GnuCash account mapping | Seed for the export (Phase 6) |
| [message-templates.yaml](message-templates.yaml) | Text message wording and consent | Seed for templates (Phase 4) |
| [public-api-shapes.yaml](public-api-shapes.yaml) | The shape of every public API answer the website reads | The contract the real API (`app/publicapi/test_contract.py`) and the website's fake API (`site/tests/unit/contract.test.mjs`) are both tested against |
| [consent-wording.yaml](consent-wording.yaml) | The two text consent checkboxes' exact wording, by version | Read by the public API, which serves the current version and records the words shown with each answer |
| [business.yaml](business.yaml) | Contact details, brand, profiles | Reference |
| [phases.yaml](phases.yaml) | Build phases and status | Reference |
| [portfolio-include.txt](portfolio-include.txt) | The paths the public portfolio copy holds, and an exclude list (decision 0111) | Read by `tools/publish-portfolio.sh` from the commit it publishes |

## Seeds and the database

PostgreSQL is the single source of truth once a feature is built. Files marked "seed" load the launch defaults; after that, the owner changes values in the control app. When a default changes, update the file in the same pull request so the documentation stays true. A later phase can add a scheduled export that rewrites these files from the database, so an AI reading them always sees live values.
