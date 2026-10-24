---
title: Secrets architecture
summary: How every key, password and token is kept in Bitwarden Secrets Manager, how the server holds one encrypted token, and how secrets reach containers without touching disk.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-23
tags: [security, secrets, bitwarden, systemd]
related: [data/configuration.yaml, docs/decisions/0028-secrets-in-bitwarden.md, docs/decisions/0041-backup-password-paper-copy.md, docs/operations/secrets-management.md]
---

# Secrets architecture

The owner's rule: every key, password and token lives in Bitwarden Secrets Manager, and no secret is stored in plaintext anywhere if it can be avoided. That includes the repository, the server's disk, Docker's configuration files, logs and backups.

## Where secrets live

- **Bitwarden Secrets Manager project "Dixie Detail"** holds every secret the system uses. The list of names, with what uses each one, is in [data/configuration.yaml](../../data/configuration.yaml). Values never appear in the repository.
- **Machine account `server`** can read that project and nothing else. The server uses it to fetch secrets. (It was named `dixie-server` until 2026-10-23.)
- **The machine account's access token**, labeled `dixie-server` in Bitwarden, is the only secret stored on the server. It is encrypted with `systemd-creds` at `/etc/credstore.encrypted/dixie-bws-token.cred`, locked to both the server's TPM chip and a root-only host key (`--with-key=host+tpm2`). A copy of the drive alone cannot decrypt it.

## How a service gets its secrets

1. A systemd unit such as `dixie-stack.service` declares `LoadCredentialEncrypted=bws-token:/etc/credstore.encrypted/dixie-bws-token.cred`. systemd decrypts the token into the unit's private, in-memory credentials directory when the unit starts.
2. The unit's script, `ops/stack-start.sh`, reads the token, and the Bitwarden CLI `bws` lists every secret in the project named by `BWS_PROJECT_ID`. `bws` is pointed at Bitwarden's US cloud with `BWS_SERVER_URL=https://vault.bitwarden.com`, and runs with a temporary settings file in `/dev/shm` that turns off its on-disk state file; the file is deleted straight after.
3. The script writes each secret to `/run/dixie-stack/secrets`, an in-memory folder only root can open, as one file per container that needs it. Each file belongs to the user that container runs as, and only that user can read it. Compose mounts the files into the containers at `/run/secrets/<name>`, and the containers' environment holds only the file paths, such as `POSTGRES_PASSWORD_FILE`. Secrets are never passed as Docker environment variables, because Docker saves those in its configuration files on disk.
4. Every start recreates all the containers, so they always mount the files just written. When the unit stops, systemd deletes `/run/dixie-stack`.

Scripts look secrets up by name in that list, through the shared helper `ops/lib/bws.sh`: each run fetches the list once with `bws_load` and reads every secret it needs from that one result with `bws_get`, and when Bitwarden is rate-limiting the machine account ("429 Too Many Requests") it waits 65 seconds and tries again, up to 3 times, logging each retry; by hand, the same lookup is `bws secret list | jq -r '.[] | select(.key=="NAME") | .value'`. `bws secret get` needs a secret's ID, not its name. A name in the code must match the name in Bitwarden exactly, capitals included; a missing name stops the script with "Bitwarden secret NAME: expected 1, found 0".

## Secrets used outside the stack

- **The GitHub deploy key** (`DEPLOY_SSH_KEY`) is loaded by `ops/deploy.sh` into a private `ssh-agent`, with a five-minute limit, only for a pull, then the agent is stopped. No key file sits in `~/.ssh`.
- **Backups** fetch `RESTIC_PASSWORD`, `RCLONE_CONFIG_PASS` and `HEALTHCHECKS_BACKUP_URL` only while the backup runs. `ops/restore-test.sh` and `ops/restic.sh` fetch the two passwords the same way, decrypting the token with `systemd-creds` because they are run by hand.
- **The public health check** fetches `HEALTHCHECKS_PUBLIC_URL` on each run, only after the health page has answered. rclone's configuration file, which holds the Google sign-in, is itself encrypted with `RCLONE_CONFIG_PASS`.
- **Workstation Git** uses HTTPS with the GitHub CLI's sign-in kept in the GNOME login keyring, so there is no SSH key or plaintext token on the Fedora machine either.

## What is not a secret

- `.env` holds settings only: host names, the database name and user, the Bitwarden project ID and server address, the deploy remote, backup paths and public URLs. The time zone is not a setting; the app is fixed to Eastern time. The full list is in [data/configuration.yaml](../../data/configuration.yaml).
- The Google Maps key used by the website's address field is public by design, because every visitor's browser receives it. It is restricted to `dixiedetail.com` and to the Maps services it needs. The server-side Maps key is a secret.

## The one exception

`RESTIC_PASSWORD`, which encrypts the off-site backups, also has a copy in the owner's Bitwarden password vault and a sealed paper copy the owner keeps away from the server. Without it nobody can open the off-site backups, so it must survive even the loss of the Bitwarden account. See [decision 0041](../decisions/0041-backup-password-paper-copy.md).

## Trade-offs accepted

- **A cold start needs Bitwarden.** Running containers keep working through a Bitwarden outage, but starting the stack needs Bitwarden reachable. The start script does not retry: if Bitwarden cannot be reached, the start fails, and `sudo systemctl restart dixie-stack` starts it once Bitwarden is back.
- **Development and tests use no Bitwarden at all.** They use made-up values in `app/dixie/settings_dev.py`, which the production image leaves out. See [decision 0045](../decisions/0045-development-made-up-values.md).
