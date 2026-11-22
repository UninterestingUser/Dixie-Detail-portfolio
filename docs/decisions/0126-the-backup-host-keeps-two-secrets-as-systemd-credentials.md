---
id: 126
title: "The backup host has no Bitwarden access and keeps its two secrets as systemd credentials"
summary: "The backup host keeps RESTIC_PASSWORD and its ping URL as systemd credentials, pasted once, and has no Bitwarden access: a narrow exception to fetching secrets at run time."
date: 2026-11-22
area: security
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [docs/decisions/0028-secrets-in-bitwarden.md, docs/decisions/0127-hourly-backups-to-the-backup-host-and-nightly-to-backblaze.md, docs/architecture/secrets.md, docs/operations/secrets-management.md, ops/backup-host/credentials.sh, ops/backup-host/dixie-backup-host-weekly.service, data/configuration.yaml]
---

# 0126: The backup host has no Bitwarden access and keeps its two secrets as systemd credentials

**Status:** accepted · **Date:** 2026-11-22 · **Area:** security

## Context

Production moves to a dedicated host, and the current server becomes the backup host: it keeps the backup server's repository, prunes it, runs the weekly restore test, and is the fallback if the production host dies (decision 0127, review finding H3). It also runs software that has nothing to do with the business.

Every other script fetches its secrets from Bitwarden at run time with the machine-account token (decision 0028). Giving the backup host that token would let anything on it read every production secret: the database password, the tunnel token, the Django key. The backup host needs only two secrets:

- `RESTIC_PASSWORD`, to prune its repository and run the restore test;
- `HEALTHCHECKS_BACKUP_HOST_URL`, to ping the weekly job's check.

## Decision

- **No Bitwarden machine account on the backup host.** Its scripts and units never load a Bitwarden token or call `bws`; `tools/test-bws.sh` checks this.
- **Two systemd credentials.** `ops/backup-host/credentials.sh`, run as root, asks the owner for each value, pasted from Bitwarden and never echoed or logged, and encrypts it with `systemd-creds --with-key=host+tpm2` (the host's TPM plus its root-only host key) to `/etc/credstore.encrypted/dixie-restic-password.cred` and `/etc/credstore.encrypted/dixie-healthchecks-backup-host-url.cred`. The values go through a pipe to `systemd-creds` only, never on a command line or to disk in plain text. It checks a pasted `RESTIC_PASSWORD` against the repository (or asks for it twice when there is none yet), so a typo can't lock the weekly job out.
- **Refreshing them** after a rotation is the same command, with the name: `sudo /srv/dixie-detail/ops/backup-host/credentials.sh RESTIC_PASSWORD`.
- **The weekly unit** loads both with `LoadCredentialEncrypted=` into its private in-memory credentials directory.
- **rest-server stores only a hash.** `BACKUP_REST_PASSWORD`, which the production host uses to reach the backup server, is pasted once into `ops/backup-host/setup.sh`, which stores only its bcrypt hash (`htpasswd -B`) for rest-server.
- **One project.** Every secret, these included, stays in the one Bitwarden project "Dixie Detail"; Bitwarden remains where each value is kept and changed.

This is a narrow exception to fetching secrets at run time: two values, on one host, still encrypted at rest and never in plain text, like the Bitwarden token itself and the health check's credential (decision 0125).

## Alternatives considered

- **A second Bitwarden machine account and project for the backup host.** Bitwarden can limit a machine account to one project, which would keep production secrets out of reach. It means two projects to keep in step and a second token on disk anyway; the owner chose one project.
- **The same machine account as production.** Rejected: the backup host would read every production secret.
- **Plain files readable only by root.** Rejected: a copy of the disk would hold them in plain text.

## Consequences

- A rotation of `RESTIC_PASSWORD` or of the backup host's ping URL needs the owner at the backup host, to paste the new value. The docs say so.
- If the backup host's TPM is reset (a firmware update can do it), the two credentials stop decrypting and must be pasted again; the weekly job's failure ping says so.
- If the production host dies and the backup host takes over production, it needs the Bitwarden token again, encrypted as on the production host (docs/operations/when-its-down.md).
