---
title: Settings and secrets reference
summary: How the system's configuration is split between non-secret settings in .env and secrets in Bitwarden, with rules for adding or renaming either.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-13
tags: [configuration, settings, secrets, env]
related: [data/configuration.yaml, docs/architecture/secrets.md, docs/operations/secrets-management.md, docs/operations/deploying-changes.md]
---

# Settings and secrets reference

Every value the system needs at run time is either a **setting**, which is not secret and lives in `/srv/dixie-detail/.env` on the server, or a **secret**, which lives only in the Bitwarden Secrets Manager project "Dixie Detail". The complete list of both, with what each is for and which phase adds it, is in [data/configuration.yaml](../../data/configuration.yaml).

## Settings in .env

- `.env` is created on the server by copying `.env.example` and filling in the values. It is never committed.
- `.env.example` in the repository lists every setting with an example or blank value, plus the names (never values) of the Bitwarden secrets.
- After a pull that changes `.env.example`, compare it with `.env` and add any new settings. The command is in [../operations/deploying-changes.md](../operations/deploying-changes.md).
- After changing `.env`, run `sudo systemctl restart dixie-stack` so the containers pick up the change.

## Secrets in Bitwarden

- Secrets are created in the Bitwarden web app, in the Dixie Detail project, with Bitwarden's generator for passwords, so no value passes through a file.
- A secret's name in Bitwarden must match the name the code asks for exactly, capitals included. A mismatch stops the stack with "expected 1, found 0".
- Scripts fetch secrets by name at start-up. See [../architecture/secrets.md](../architecture/secrets.md).

## Adding or renaming a setting or secret

One pull request changes, together:

1. The code that reads it.
2. `.env.example` (a setting's line, or a secret's name in the comment list).
3. [data/configuration.yaml](../../data/configuration.yaml).
4. Any doc that names it.

Then, on the server, add the setting to `.env` or create or rename the secret in Bitwarden before restarting the stack.
