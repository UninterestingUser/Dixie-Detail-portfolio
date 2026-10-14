---
id: 50
title: "django-simple-history records changes to the pricebook, customers, vehicles and appointments"
summary: "django-simple-history keeps every earlier version of pricebook, customer, vehicle and appointment records, with who changed it and when, so changes can be traced and undone."
date: 2026-10-14
area: stack
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/control-app.md, docs/reference/pricebook-changes.md, docs/architecture/data-model.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md]
---

# 0050: django-simple-history records changes to the pricebook, customers, vehicles and appointments

**Status:** accepted · **Date:** 2026-10-14 · **Area:** stack

## Context

The control app must record who changed every price or description, and when, and allow the change to be undone. The same need applies to customer, vehicle and appointment records, which the owner and future helpers will edit by hand.

## Decision

The Django package `django-simple-history` keeps a history table for each pricebook, customer, vehicle and appointment model. Every save adds a row with the record's earlier values, who made the change, when, and the kind of change (created, changed or deleted). The control app can show a record's history and put an earlier version back.

Change history is not the same as pricebook versions (decision 0033). A pricebook version is a published state that bookings refer to. The history is the trail of every edit, published or not.

## Alternatives considered

- **A hand-written audit table.** Repeats what a maintained package already does, with more code to test.
- **django-reversion.** Stores versions as serialized text rather than ordinary tables, which makes history harder to query and report on.
- **PostgreSQL triggers.** Do not know which signed-in person made a change.

## Consequences

Each tracked model gets a second table, included in backups. Removing a customer's personal data must also remove it from the history tables. Edits made by scripts, such as the Baserow import, are recorded with a note saying where they came from instead of a person.
