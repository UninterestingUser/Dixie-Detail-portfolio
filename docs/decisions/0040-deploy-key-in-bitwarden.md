---
id: 40
title: "The server pulls with a read-only deploy key kept in Bitwarden"
summary: "A read-only GitHub deploy key, generated in memory and stored only in Bitwarden, is loaded into ssh-agent for each pull."
date: 2026-10-12
area: security
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/operations/deploying-changes.md]
---

# 0040: The server pulls with a read-only deploy key kept in Bitwarden

**Status:** accepted · **Date:** 2026-10-12 · **Area:** security

## Context

The server must pull the private repository without storing a key on disk.

## Decision

Generate the key in /dev/shm, add the public half to GitHub with write access off, save the private half as `DEPLOY_KEY`, delete both files. Pulls load it into ssh-agent and stop the agent afterwards.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

No key file in ~/.ssh. Pulls need the Bitwarden token.
