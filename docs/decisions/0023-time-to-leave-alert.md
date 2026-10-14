---
id: 23
title: "Time-to-leave alert at drive time plus 10 minutes"
summary: "Each job pushes an alert at drive time plus 10 minutes before the start, using predicted traffic."
date: 2026-10-07
area: alerts
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md]
---

# 0023: Time-to-leave alert at drive time plus 10 minutes

**Status:** accepted · **Date:** 2026-10-07 · **Area:** alerts

## Context

The owner wanted to know when to leave without checking a map.

## Decision

A push notification from the control app to every assigned staff member, with navigation and an "On my way" button, plus a "Drive to job" block on the Jobs calendar as backup.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Needs Google Maps Platform for traffic-aware drive times.
