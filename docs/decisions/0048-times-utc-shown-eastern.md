---
id: 48
title: "Times are stored in UTC and shown in Eastern"
summary: "Every moment in time is stored in UTC and shown in Eastern time, so daylight saving changes never make a stored time ambiguous."
date: 2026-10-14
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md, docs/reference/data-migration.md, docs/architecture/data-model.md]
---

# 0048: Times are stored in UTC and shown in Eastern

**Status:** accepted · **Date:** 2026-10-14 · **Area:** scheduling

## Context

The business works in Eastern time, which moves between EST and EDT twice a year. On the November change, the hour from 1:00 to 2:00 AM happens twice, so a local time on its own can be ambiguous. Google Calendar, Stripe, Quo and the Baserow export all exchange times in UTC or with an offset.

## Decision

- Every moment in time, such as an arrival time, a payment or a text sent, is stored in UTC, as PostgreSQL `timestamp with time zone` through Django with `USE_TZ = True`.
- Everything customer-facing and every control app screen shows Eastern time (`America/New_York`), the app's `TIME_ZONE`. The time zone is fixed in the code, not a setting.
- Times entered in the control app are read as Eastern and converted to UTC when saved.
- A calendar day with no time of day, such as a day closure, is stored as a plain date.

## Alternatives considered

- **Store Eastern local times.** Ambiguous for one hour each November, and every exchange with an outside service would need converting.

## Consequences

Daylight saving changes are handled by the time zone database, not by hand. The Baserow import converts its UTC times as [data-migration.md](../reference/data-migration.md) describes. Scheduling tests should include the two days a year the clocks change.
