---
id: 28
title: "Every secret lives in Bitwarden Secrets Manager"
summary: "All keys, passwords and tokens live in Bitwarden Secrets Manager; the server stores only the machine-account token, encrypted and bound to the TPM."
date: 2026-10-13
area: security
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/secrets.md, data/configuration.yaml]
---

# 0028: Every secret lives in Bitwarden Secrets Manager

**Status:** accepted · **Date:** 2026-10-13 · **Area:** security

## Context

The owner uses Bitwarden Secrets Manager for all secrets and wants nothing secret stored in plaintext anywhere if possible.

## Decision

Project "Dixie Detail" holds every secret; machine account `dixie-server` reads it. The token is encrypted with `systemd-creds --with-key=host+tpm2`. Services load it with `LoadCredentialEncrypted=`, fetch secrets with `bws`, and pass them to containers as in-memory files, never Docker environment variables. `.env` holds settings only.

## Alternatives considered

- **Secrets in `.env`.** Plaintext on disk; against the owner's policy.
- **Docker secrets or environment variables.** Environment variables are saved in Docker's config on disk.

## Consequences

A cold start needs Bitwarden reachable. Names in code must match Bitwarden exactly. The deploy key, backup passwords and ping URLs are secrets too.
