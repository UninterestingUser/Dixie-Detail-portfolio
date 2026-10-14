---
id: 43
title: "Workstation Git over HTTPS with the GitHub CLI keyring"
summary: "The Fedora workstation uses HTTPS for Git, with the GitHub CLI's sign-in kept in the GNOME login keyring."
date: 2026-10-13
area: security
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/operations/workstation-setup.md]
---

# 0043: Workstation Git over HTTPS with the GitHub CLI keyring

**Status:** accepted · **Date:** 2026-10-13 · **Area:** security

## Context

The owner's no-plaintext-secrets policy applies to the workstation too.

## Decision

Choose HTTPS in `gh auth login` and let gh act as Git's credential helper. `gh auth status` should show "(keyring)".

## Alternatives considered

- **SSH with a key file.** A second credential on disk.
- **The Bitwarden desktop SSH agent.** Keeps keys in the vault; an option for later.

## Consequences

No SSH key or plaintext token on the workstation.
