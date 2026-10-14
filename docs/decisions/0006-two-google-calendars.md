---
id: 6
title: "Two Google Workspace calendars: Jobs and Time Off"
summary: "One calendar the system writes (Jobs) and one the owner writes (Time Off), so system events and owner blocks never mix."
date: 2026-10-07
area: calendar
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md]
---

# 0006: Two Google Workspace calendars: Jobs and Time Off

**Status:** accepted · **Date:** 2026-10-07 · **Area:** calendar

## Context

The owner wanted appointments on a phone calendar and a simple way to close days.

## Decision

Create "Dixie Detail Jobs" (system writes, one event per appointment) and "Dixie Detail Time Off" (owner writes; an all-day event closes the day) under the owner's Workspace account, shared with a service account. Customers are never added as guests.

## Alternatives considered

- **One shared calendar.** The system could mistake its own events for days off.

## Consequences

Either calendar can be shared with a helper later. Edits to Jobs events in Google are overwritten at the next sync. Created 2026-10-11.
