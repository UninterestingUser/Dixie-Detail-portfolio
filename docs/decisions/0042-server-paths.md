---
id: 42
title: "Server paths: code at /srv/dixie-detail, backups at /mnt/raid/Backups/dixie-detail"
summary: "The repository checkout lives at /srv/dixie-detail on the NVMe drive, and backups at /mnt/raid/Backups/dixie-detail on the RAID."
date: 2026-10-13
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/server-and-stack.md]
---

# 0042: Server paths: code at /srv/dixie-detail, backups at /mnt/raid/Backups/dixie-detail

**Status:** accepted · **Date:** 2026-10-13 · **Area:** infrastructure

## Context

The first stack build assumed /opt/dixie-detail, which broke the service; the owner also renamed the backup folder with a capital B.

## Decision

Use these two paths everywhere, recorded in CLAUDE.md and the docs.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Any script or unit naming another path is a bug.
