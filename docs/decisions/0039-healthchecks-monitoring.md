---
id: 39
title: "Healthchecks.io for outside monitoring"
summary: "Healthchecks.io watches the nightly backup and the public path, emailing the owner when either stops checking in."
date: 2026-10-12
area: monitoring
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/backups-and-monitoring.md]
---

# 0039: Healthchecks.io for outside monitoring

**Status:** accepted · **Date:** 2026-10-12 · **Area:** monitoring

## Context

The plan called for an outside monitor of the booking service from launch.

## Decision

Two checks on the free plan: nightly backup (daily, 2 hours' grace) and public address (every 10 minutes, 5 minutes' grace), pinged by the server after it fetches `https://api.dixiedetail.com/health`.

## Alternatives considered

- **UptimeRobot.** Its free plan has been non-commercial since October 2024.

## Consequences

Ping URLs are Bitwarden secrets. One check covers the server, power, internet, tunnel and app together.
