---
id: 22
title: "Timing of the second Monthly Maintenance job"
summary: "The second Monthly job starts at the first job's scheduled end plus the drive time between them, minimum 30 minutes, rounded up to the quarter hour."
date: 2026-10-07
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md]
---

# 0022: Timing of the second Monthly Maintenance job

**Status:** accepted · **Date:** 2026-10-07 · **Area:** booking

## Context

Two Monthly jobs can share a day, so the second needs a start time.

## Decision

Start = first job's end + max(drive time, 30 minutes), rounded up to the next quarter hour. Example: 8:00 + 3 hours + 42-minute drive = 11:45.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Open point: the rounding to the quarter hour was proposed during planning and is not yet confirmed by the owner; the 30-minute minimum is the owner's rule.
