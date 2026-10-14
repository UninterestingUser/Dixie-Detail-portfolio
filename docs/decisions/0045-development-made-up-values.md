---
id: 45
title: "Development and tests use made-up throwaway values, not Bitwarden"
summary: "Development and automated tests use made-up values in a development-only settings file that the production image leaves out, so no secret is needed off the server."
date: 2026-10-14
area: security
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/architecture/secrets.md, docs/operations/workstation-setup.md, data/configuration.yaml]
---

# 0045: Development and tests use made-up throwaway values, not Bitwarden

**Status:** accepted · **Date:** 2026-10-14 · **Area:** security

## Context

Phase 1 adds automated tests that must run the same way on the Fedora workstation and on GitHub Actions. The earlier rule in `CLAUDE.md` said local development would use a separate Bitwarden project with throwaway values. Following it would mean storing a Bitwarden access token on the workstation and in GitHub, which is one more secret to guard, only to fetch values that protect nothing.

## Decision

Development and tests use made-up values written in `app/dixie/settings_dev.py`, committed to the repository. The values open only a throwaway PostgreSQL database that `tools/run-tests.sh` starts in memory, with no published port, and removes after the run.

Production can never load that file:

- `app/.dockerignore` leaves `dixie/settings_dev.py` out of the production image.
- `tools/run-tests.sh` builds the production image on every run, locally and on GitHub, and fails if the image can import `dixie.settings_dev`.
- The production settings, `dixie.settings`, never import it.

A real secret is never written into the development settings. Production secrets stay in Bitwarden, as decision 0028 sets out.

## Alternatives considered

- **A separate Bitwarden project for development.** Needs a machine-account token on the workstation and in GitHub's secrets, which adds two places a token can leak, for values that guard nothing.
- **Development values in environment variables or a `.env` file.** Easy to mix up with production settings, and the values would still have to come from somewhere for GitHub Actions.

## Consequences

Anyone with the repository can run the tests with one command and no sign-in. GitHub Actions needs no secrets. If a later phase needs a real sandbox key for an outside service, such as a test-mode payment key, that is a new decision.
