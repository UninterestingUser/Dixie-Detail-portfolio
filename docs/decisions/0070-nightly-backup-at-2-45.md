---
id: 70
title: "The nightly backup runs at 2:45 AM, clear of the public health check"
summary: "The backup moves from 2:30 to 2:45 AM Eastern (3:45 AM on the spring-forward Sunday) so it never calls Bitwarden in the same minute as the 10-minute public health check."
date: 2026-10-18
area: backups
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-18
supersedes: []
superseded_by: []
related: [ops/dixie-backup.timer, docs/architecture/backups-and-monitoring.md, docs/operations/troubleshooting.md, docs/decisions/0027-backups-to-google-drive.md]
---

# 0070: The nightly backup runs at 2:45 AM, clear of the public health check

**Status:** accepted · **Date:** 2026-10-18 · **Area:** backups

## Context

Decision 0027 set the nightly backup at 2:30 AM. The public health check runs every 10 minutes, on the hour and at :10, :20, :30, :40 and :50, so every night both started at 2:30 and called Bitwarden Secrets Manager in the same minute with the same machine account. Bitwarden answered "429 Too Many Requests", and the backup failed. The scripts now retry a 429, but the clash itself is avoidable.

## Decision

- The backup runs at 2:45 AM Eastern, between two health-check runs.
- On the Sunday clocks spring forward, when 2:45 AM does not exist, it runs at 3:45 AM, also clear of the health check.
- Everything else in decision 0027 stands. The Healthchecks backup check expects one ping a day with 2 hours' grace, so it needs no change.

## Alternatives considered

- **A random delay on the health check timer.** Would spread its calls but could still land on the backup's minute.
- **Rely on the retry alone.** Works, but makes the backup wait up to three minutes every night for no reason.

## Consequences

The backup and the health check no longer start together. A new timer that calls Bitwarden should also avoid the health check's 10-minute marks.
