---
id: 58
title: "Service times in the price matrix exclude setup and breakdown"
summary: "The price matrix holds one-person service time only: every main service drops by 1 hour, Headlight Restoration is 1.5 hours, extractions are unchanged, and prices stay the same."
date: 2026-10-17
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [data/price-matrix.csv, data/pricing-rules.yaml, docs/reference/pricing.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md, docs/decisions/0017-two-person-crew-time.md, docs/decisions/0019-second-person-flag-at-8-hours.md]
---

# 0058: Service times in the price matrix exclude setup and breakdown

**Status:** accepted · **Date:** 2026-10-17 · **Area:** pricing

## Context

The owner's matrix hours included setup and breakdown. Decision 0056 makes setup and breakdown scheduling settings that divide between the people on a job, so leaving them inside the matrix hours would count them twice and scale them wrongly with crew size.

## Decision

- The price matrix holds **service time only**. Its hours column is renamed from `one_person_hours` to `one_person_service_hours`.
- **New one-person service hours:** Full Detail, Interior Only, Exterior Only, 1-Step and 2-Step Paint Correction each drop by 1 hour, and Quarterly and Monthly Maintenance follow Full Detail. Carpet Extraction and Seat Extraction are unchanged. Headlight Restoration is 1.5 hours (2.5 hours on site for one person).
- **Prices are unchanged.** All 90 rows keep the same price.
- **The full-day flag** is 8 hours of one-person time on site, which is 7 one-person service hours: the same jobs as before.
- The worked RAV4 example becomes Full Detail $250 / 5 hours, condition level 2 +$25, Seat Extraction $80 / 1.5 hours: $355, 6.5 hours of service, 7.5 hours on site.

## Alternatives considered

- **Keep setup and breakdown inside the matrix hours.** Two people would then take 60% of the setup too, and changing setup time would mean editing 90 rows.

## Consequences

The hour figures quoted in decisions 0015, 0017 and 0018 were in the old hours that included setup and breakdown; those decisions' rules are unchanged, and the current figures are in `data/price-matrix.csv` and `docs/reference/pricing.md`. The 8-hour threshold of decision 0019 now reads as one-person time on site. The pricebook load in Phase 1 Step 3 uses the new hours. Code from Steps 1 and 2 still calls the field `one_person_hours`; Step 3 renames it.
