---
id: 22
title: "Timing of the second Monthly Maintenance job"
summary: "The second Monthly job starts at the first job's scheduled end plus the drive time between them, minimum 30 minutes, rounded up to the quarter hour."
date: 2026-10-07
area: booking
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: [docs/decisions/0056-scheduling-rules-are-settings.md]
related: [docs/reference/scheduling-and-calendars.md]
---

# 0022: Timing of the second Monthly Maintenance job

**Status:** superseded by [0056](0056-scheduling-rules-are-settings.md) · **Date:** 2026-10-07 · **Area:** booking

## Context

Two Monthly jobs can share a day, so the second needs a start time.

## Decision

Start = first job's end + max(drive time, 30 minutes), rounded up to the next quarter hour. Example: 8:00 + 3 hours + 42-minute drive = 11:45.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Open point: the rounding to the quarter hour was proposed during planning and is not yet confirmed by the owner; the 30-minute minimum is the owner's rule.

## Superseded

Superseded on 2026-10-17 by [decision 0056](0056-scheduling-rules-are-settings.md): the gap and its rounding are now the launch values of the gap-before-a-later-job and rounding settings, and they apply to any two jobs allowed to share a day. The quarter-hour rounding is still not confirmed by the owner.
