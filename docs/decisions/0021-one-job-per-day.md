---
id: 21
title: "One job per day, except two Monthly Maintenance jobs"
summary: "Each day takes one job whatever its length, except that two Monthly Maintenance jobs can share a day; maintenance is booked by the owner only."
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

# 0021: One job per day, except two Monthly Maintenance jobs

**Status:** superseded by [0056](0056-scheduling-rules-are-settings.md) · **Date:** 2026-10-07 · **Area:** booking

## Context

The owner works one job a day; Monthly Maintenance visits are short with two people.

## Decision

Capacity is one job per day. Monthly and Quarterly Maintenance never appear on the website.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

See decision 0022 for timing the second Monthly job.

## Superseded

Superseded on 2026-10-17 by [decision 0056](0056-scheduling-rules-are-settings.md): one job a day and two Monthly Maintenance jobs sharing a day are now the launch values of the jobs-per-day and services-that-can-share-a-day settings. Monthly and Quarterly Maintenance are still booked only by the owner.
