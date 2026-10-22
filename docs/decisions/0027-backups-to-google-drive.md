---
id: 27
title: "Nightly backups to the RAID and to Google Drive with restic"
summary: "Nightly dumps go to the RAID, and an encrypted restic copy goes to the owner's Google Workspace Drive through rclone."
date: 2026-10-13
area: backups
status: superseded
audience: [owner, developer]
visibility: restricted
updated: 2026-10-22
supersedes: []
superseded_by: [docs/decisions/0070-nightly-backup-at-2-45.md]
related: [docs/architecture/backups-and-monitoring.md]
---

# 0027: Nightly backups to the RAID and to Google Drive with restic

**Status:** superseded by [0070](0070-nightly-backup-at-2-45.md) for the backup time · **Date:** 2026-10-13 · **Area:** backups

## Context

RAID survives a failed disk but not deletion, corruption, fire or theft. The owner already pays for Workspace storage.

## Decision

Dump at 2:30 AM to `/mnt/raid/Backups/dixie-detail` (14 daily, 12 monthly), then restic to `rclone:gdrive:dixie-detail-backups`, with the rclone remote limited to files it creates.

## Alternatives considered

- **Backblaze B2.** A small extra monthly cost for storage the owner already has.

## Consequences

No added cost. Backups depend on `RESTIC_PASSWORD`; see decision 0041.
