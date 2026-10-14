---
id: 33
title: "Pricebook versions with line snapshots on every appointment"
summary: "Each appointment stores a snapshot of its lines; pricebook edits are published as numbered versions with an effective date, and booked jobs change only by the owner's choice."
date: 2026-10-11
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/pricebook-changes.md]
---

# 0033: Pricebook versions with line snapshots on every appointment

**Status:** accepted · **Date:** 2026-10-11 · **Area:** pricing

## Context

The owner required that past jobs never change, and that future booked jobs be handled case by case when prices change.

## Decision

Publish drafts as versions. On publish, list affected booked jobs and ask per job: keep booked price (default), use new price or a custom amount, with bulk options and series-level choices. Log every choice.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Sales tax is not part of this; it uses the rate on the day of service.
