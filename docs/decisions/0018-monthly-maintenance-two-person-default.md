---
id: 18
title: "Monthly Maintenance defaults to a two-person crew"
summary: "Monthly Maintenance assumes two people by default; every other service assumes one."
date: 2026-10-07
area: crew
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md]
---

# 0018: Monthly Maintenance defaults to a two-person crew

**Status:** accepted · **Date:** 2026-10-07 · **Area:** crew

## Context

The spreadsheet's Monthly Maintenance times already assumed two people.

## Decision

Store one-person hours for Monthly Maintenance (equal to Full Detail) and default its crew to two, giving 2.5 to 4.5 hours.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Two Monthly jobs can fit in a day; see decision 0021.
