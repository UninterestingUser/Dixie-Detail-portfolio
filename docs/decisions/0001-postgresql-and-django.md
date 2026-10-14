---
id: 1
title: "PostgreSQL and Django for the database, API and control app"
summary: "One PostgreSQL database with a Django core app, because Django ships logins, permissions, migrations and an admin screen for every table."
date: 2026-10-07
area: stack
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/system-overview.md]
---

# 0001: PostgreSQL and Django for the database, API and control app

**Status:** accepted · **Date:** 2026-10-07 · **Area:** stack

## Context

The business needed one store for customers, appointments, pricing, billing, staff, bookkeeping and marketing, plus a back-office app, built and maintained by one owner with AI help.

## Decision

PostgreSQL is the single source of truth. Django (Python) provides the business logic, the REST API, the control app and scheduled jobs, all in one service.

## Alternatives considered

- **An off-the-shelf admin tool such as Directus.** Starts faster, but pricing rules, availability and promotions need custom code either way.
- **Separate SaaS tools.** That is the current situation, with data entered in several places.

## Consequences

Most of a back-office app comes built in. Every later phase builds on the same models. Everything runs in Docker on the home server.
