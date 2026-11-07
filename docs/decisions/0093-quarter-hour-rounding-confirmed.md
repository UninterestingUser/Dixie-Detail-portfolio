---
id: 93
title: "A later job's start is rounded up to the next quarter hour"
summary: "The owner confirmed on 2026-11-04 that a later job's earliest start is rounded up to the next quarter hour; 15 minutes is the launch value of the rounding setting."
date: 2026-11-04
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-07
supersedes: [docs/decisions/0022-second-monthly-job-timing.md]
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md, data/booking-rules.yaml, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0022-second-monthly-job-timing.md, docs/decisions/0094-how-the-availability-check-places-and-shares.md]
---

# 0093: A later job's start is rounded up to the next quarter hour

**Status:** accepted · **Date:** 2026-11-04 · **Area:** scheduling

## Context

Decision 0022 set the start of a second Monthly Maintenance job as the first job's end plus the drive between them, at least 30 minutes, rounded up to the next quarter hour. The 30-minute minimum was the owner's rule, but the rounding had been proposed during planning and was never confirmed. Decision 0056 made the gap and its rounding settings and kept 15 minutes as the proposed launch value of the rounding. The availability check, built in Phase 3, Step 2, needs a settled value.

## Decision

- **Round a later job's earliest start up to the next quarter hour.** The owner confirmed it on 2026-11-04. 15 minutes is the launch value of the rounding setting (`gap_between_jobs.round_start_up_to_minutes` in `data/booking-rules.yaml`).
- The rule is unchanged otherwise: a later job starts no earlier than the earlier job's end, after breakdown, plus the drive between the two addresses, at least 30 minutes, then rounded up. An 8:00 job of 3 hours on site followed by a 42-minute drive gives 11:42, rounded up to 11:45.
- The rounding stays a setting on the control app's scheduling settings screen. The steps offered divide the hour (1, 5, 10, 15, 20, 30 or 60 minutes), so a rounded time is the same on the Eastern clock all year.

## Alternatives considered

- **No rounding.** A second job could start at 11:42, an awkward time to give a customer and to keep to.
- **Round to the nearest quarter hour.** Could round down below the drive time or the 30-minute minimum.

## Consequences

The open point left by decisions 0022 and 0056 is closed, and the owner action to confirm or drop the rounding is done. Decision 0022 is superseded by this record for its rounding and by decision 0056 for the rest.
