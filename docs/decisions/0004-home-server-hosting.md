---
id: 4
title: "Business data on the owner's home server"
summary: "The database and core app run on the owner's home server, with a cloud server as a fallback if outages recur."
date: 2026-10-07
area: hosting
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/server-and-stack.md]
---

# 0004: Business data on the owner's home server

**Status:** accepted · **Date:** 2026-10-07 · **Area:** hosting

## Context

The owner already runs a capable home server (Ryzen 5 5600, 16 GB, RAID 5) with a battery backup, and prefers to own the data.

## Decision

Host the Docker stack on the home server. Move the same stack to a cloud server (about $14 to $29 a month) if there is more than one outage a month during booking hours, or any outage over four hours.

## Alternatives considered

- **A cloud server from the start.** A monthly cost for capacity the home server already has.

## Consequences

No hosting cost. Outages are covered by the static site staying up, booking requests queuing at Cloudflare, battery shutdown, and outside monitoring.
