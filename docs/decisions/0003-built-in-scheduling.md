---
id: 3
title: "Build scheduling into the core app and retire Setmore"
summary: "Scheduling lives in the core app so services, durations, availability and prices share one database; Setmore is retired at launch."
date: 2026-10-07
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md]
---

# 0003: Build scheduling into the core app and retire Setmore

**Status:** accepted · **Date:** 2026-10-07 · **Area:** scheduling

## Context

Setmore cannot apply the business's pricing or capacity rules, cannot export appointments, and duplicates customer data.

## Decision

The core app owns availability, booking and the calendar. Google Calendar is a mirror and a source of days off.

## Alternatives considered

- **Keep Setmore.** It cannot carry the pricing, the one-job-per-day rule or compliant text consent.

## Consequences

Nothing is entered twice. The booking flow, calendar and pricebook read the same records. Setmore stays live until launch.
