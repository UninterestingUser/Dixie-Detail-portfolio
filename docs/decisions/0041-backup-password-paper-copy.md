---
id: 41
title: "The backup password also has a vault copy and a sealed paper copy"
summary: "RESTIC_PASSWORD is the one secret allowed outside Secrets Manager: a copy in the owner's Bitwarden password vault and a sealed paper copy."
date: 2026-10-13
area: security
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/secrets.md]
---

# 0041: The backup password also has a vault copy and a sealed paper copy

**Status:** accepted · **Date:** 2026-10-13 · **Area:** security

## Context

Without RESTIC_PASSWORD the off-site backups cannot be opened, so losing the Bitwarden account would lose the backups.

## Decision

Keep RESTIC_PASSWORD in Secrets Manager, in the owner's Bitwarden vault, and on sealed paper stored safely away from the server.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

An accepted exception to decision 0028.
