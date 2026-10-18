---
id: 64
title: "The app reads the repository's data/ folder, mounted read-only"
summary: "The core app reads the price matrix and launch values from data/ in the checkout, mounted read-only at /srv/data, instead of a copy baked into the image or the database."
date: 2026-10-17
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [compose.yaml, tools/run-tests.sh, app/dixie/settings_base.py, docs/architecture/server-and-stack.md, docs/decisions/0044-documentation-as-code.md, docs/decisions/0056-scheduling-rules-are-settings.md]
---

# 0064: The app reads the repository's data/ folder, mounted read-only

**Status:** accepted · **Date:** 2026-10-17 · **Area:** infrastructure

## Context

Phase 1 Step 3 loads the pricebook from `data/price-matrix.csv`, `data/services.yaml`, `data/pricing-rules.yaml` and `data/vehicle-classes.yaml`, and works out time on site from the setup and breakdown launch values in `data/booking-rules.yaml` until Phase 3 adds the scheduling settings. The app image is built from `app/` alone, so `data/` was not in it, and the test container mounted only `app/`.

## Decision

- The app finds `data/` through the setting `DATA_DIR`: the folder beside `app/`, which is `/srv/data` in a container whose app sits at `/srv/app`.
- `compose.yaml` mounts the checkout's `data/` read-only at `/srv/data` in the `app` container, and `tools/run-tests.sh` does the same for the tests, so the tests check the real data files.
- PyYAML is added to the app's requirements to read the YAML files.

## Alternatives considered

- **Build the image from the repository root and copy `data/` in.** Larger build context and a second copy of the facts in every image; a change to `data/` would need a rebuild to be seen.
- **Copy the launch values into the database by a migration.** Phase 3 adds the settings screen that holds them; until then a migration would duplicate `data/booking-rules.yaml` and drift from it.

## Consequences

`data/` stays the one place the facts are written (decision 0044). A deploy that changes it reaches the app on the next restart, read-only, so the app can never write to it. The pricebook itself changes only through new pricebook versions, never by reloading the files.
