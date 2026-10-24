---
title: Server and Docker stack
summary: The home server's hardware and folders, the four containers of the Phase 0 stack, and the systemd units and scripts that start, back up and watch it and refresh the vehicle data.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-24
tags: [server, docker, systemd, infrastructure]
related: [docs/architecture/network-and-access.md, docs/architecture/backups-and-monitoring.md, docs/architecture/secrets.md, docs/operations/deploying-changes.md, docs/operations/monitoring.md]
---

# Server and Docker stack

This page describes the stack as it ran at the end of Phase 0 (2026-10-13). File names under `ops/` and `compose.yaml` are the authority; if they change, update this page in the same pull request.

## The home server

| Part | Detail |
| --- | --- |
| Hostname | `grassman-server` on the LAN; `home-server` on the tailnet |
| LAN address | 192.0.2.10 |
| Operating system | Ubuntu Server, with Docker Engine and Docker Compose |
| CPU and memory | AMD Ryzen 5 5600 (6 cores, 12 threads), 16 GB DDR4, Gigabyte B550 board |
| Security chip | AMD firmware TPM, enabled in the BIOS; used to lock the Bitwarden token |
| Boot drive | Samsung 970 EVO Plus 500 GB NVMe. The code and the database live here |
| Data drives | Four 4 TB disks in mdadm RAID 5 at `/mnt/raid`, about 12 TB usable. Backups land here |
| Power | APC battery unit covering the server, firewall and modem, connected by USB; `apcupsd` shuts the server down at 20% battery or 5 minutes left |
| Updates | `unattended-upgrades` installs security updates automatically |

The workload is expected to fit in about 2 GB of memory, so the server has ample room, including for a pruned Bitcoin node in Phase 7.

Other services already run on this server, such as a FileBrowser container published on port 8080 of the LAN address. The Dixie Detail stack does not publish 8080 on the server, so they do not conflict.

## Folders

| Path | Holds |
| --- | --- |
| `/srv/dixie-detail` | The repository checkout the server runs, pulled from GitHub. `.env` lives here |
| `/mnt/raid/Backups/dixie-detail/daily` | Nightly database dumps, `dixie-detail-YYYY-MM-DD.dump`, 14 kept |
| `/mnt/raid/Backups/dixie-detail/monthly` | The first dump of each month, `dixie-detail-YYYY-MM.dump`, 12 kept |
| `/etc/credstore.encrypted/dixie-bws-token.cred` | The encrypted Bitwarden machine-account token |
| `/etc/systemd/system/dixie-*.{service,timer}` | Installed copies of the unit files from `ops/` |
| `/run/dixie-stack/secrets` | The stack's secret files, in memory, only while `dixie-stack.service` is active. See [secrets.md](secrets.md) |
| `/srv/dixie-vehicle-data` | The vehicle data import's download cache, owned by the app container's user (uid 10001); created by `ops/deploy.sh` when missing, and safe to delete. See [../operations/importing-vehicle-data.md](../operations/importing-vehicle-data.md) |

## The four containers

The Compose project is named `dixie`. Container names follow Compose's pattern, such as `dixie-db-1`.

| Container | Image (Phase 0) | Role | Reachable from |
| --- | --- | --- | --- |
| `db` | `postgres:18.6-trixie` | PostgreSQL database | The `dixie_backend` network, shared with `app` and `caddy`; only the app connects to it |
| `app` | `dixie-app:local`, built from the repo | Django core app | Caddy only |
| `caddy` | `caddy:2.11.4-alpine` | Reverse proxy with the private and public doors | Port 127.0.0.1:8000 on the server (private door); port 8080 inside the `dixie_tunnel` network (public door) |
| `cloudflared` | `cloudflare/cloudflared:2026.9.1` | Cloudflare Tunnel connector | Nothing; it dials out to Cloudflare |

The only port published on the server is `127.0.0.1:8000`, which listens on the server itself, not the LAN. See [network-and-access.md](network-and-access.md).

## How the app container starts

The `app` container applies database migrations every time it starts, before the web server starts. Its command in `app/Dockerfile` runs `python manage.py migrate --noinput` and then, only if that succeeds, replaces itself with gunicorn. This keeps the database schema in step with the code after every deploy, restart or reboot, with no manual step.

- Compose starts `app` only after the `db` healthcheck passes, so the migration never runs against a database that is still starting.
- A migration that fails stops the container before gunicorn starts, so the app never serves requests against a schema that does not match the code. The error is in `docker logs dixie-app-1`, and Compose keeps restarting the container until the cause is fixed.
- A migration that has already been applied is skipped, so a restart with no new migrations adds only a moment to start-up.
- The repository's `data/` folder is mounted read-only at `/srv/data`, beside the app at `/srv/app` (decision 0064). The pricebook load reads the price matrix and rules from it, and the time-on-site calculation reads the setup and breakdown launch values from `data/booking-rules.yaml` until Phase 3 moves them into settings. A deploy that changes a file in `data/` reaches the app on the next restart; the pricebook itself changes only through a new pricebook version.
- gunicorn runs with `--no-control-socket`. Its control socket would be created under the home folder, which the read-only container cannot write to, and nothing uses it. See [../operations/troubleshooting.md](../operations/troubleshooting.md).

## systemd units

| Unit | What it does | When |
| --- | --- | --- |
| `dixie-stack.service` | Runs `ops/stack-start.sh`: loads the Bitwarden token, fetches the secrets, writes them to in-memory files and recreates and starts every container of the Compose stack. A one-shot unit that stays "active (exited)"; stopping it runs `docker compose down` | At boot, and on `systemctl restart dixie-stack` |
| `dixie-backup.service` | Runs `ops/backup.sh`: dumps PostgreSQL to the RAID, sends it to Google Drive with restic, applies retention, pings Healthchecks | Triggered by `dixie-backup.timer` |
| `dixie-backup.timer` | Starts the backup | 2:45 AM Eastern every night, clear of the public health check's 10-minute marks (decision 0070); 3:45 AM on the Sunday clocks spring forward, when 2:45 AM does not exist. A run missed while the server was off happens at the next boot |
| `dixie-public-health.service` | Runs `ops/public-health.sh`: fetches the public health address through Cloudflare and pings Healthchecks on success | Triggered by `dixie-public-health.timer` |
| `dixie-public-health.timer` | Starts the public check | Every 10 minutes |
| `dixie-vehicle-refresh.service` | Runs `ops/vehicle-refresh.sh`: reloads the vehicle data from every source and reclassifies, holding class changes the owner relies on in the review queue, and pings Healthchecks | Triggered by `dixie-vehicle-refresh.timer` |
| `dixie-vehicle-refresh.timer` | Starts the vehicle data refresh | The first Sunday of each month at 4:15 AM Eastern, plus up to 15 minutes at random (decision 0081). A run missed while the server was off is not made up at boot |

The stack unit reads `/srv/dixie-detail/.env` as an environment file and loads the token with `LoadCredentialEncrypted=bws-token:/etc/credstore.encrypted/dixie-bws-token.cred`.

## Scripts in ops/

| Script | Purpose |
| --- | --- |
| `ops/stack-start.sh` | Fetch secrets from Bitwarden, write them to `/run/dixie-stack/secrets`, and recreate and start every container |
| `ops/deploy.sh` | Pull `DEPLOY_BRANCH` from `DEPLOY_REMOTE` with the deploy key from Bitwarden, install any new or changed unit files, enable the stack and the three timers, create the vehicle data cache folder if it is missing, rebuild the app image and restart the stack; run with `sudo` |
| `ops/backup.sh` | Nightly dump, off-site copy, retention and Healthchecks pings |
| `ops/restore-test.sh` | Restore the newest Drive snapshot into a throwaway PostgreSQL container and check it; run with `sudo` |
| `ops/restic.sh` | Run any restic command against the Drive repository with the passwords loaded, such as `init`, `snapshots` or `check`; run with `sudo` |
| `ops/public-health.sh` | The 10-minute public-path check |
| `ops/vehicle-refresh.sh` | The monthly vehicle data refresh in a one-off app container, with Healthchecks pings ([../operations/monitoring.md](../operations/monitoring.md)) |
| `ops/lib/bws.sh` | Shared Bitwarden helpers: load the token, fetch the project's secrets, look one up by name |
| `ops/lib/restic.sh` | Shared restic settings and passwords for `backup.sh`, `restore-test.sh` and `restic.sh` |
| `ops/lib/healthchecks.sh` | Shared Healthchecks ping, used by `backup.sh`, `public-health.sh` and `vehicle-refresh.sh` |
| `ops/lib/settings.sh` | Reads `.env` for scripts run by hand |
| `ops/github_known_hosts` | GitHub's SSH host keys, pinned so `deploy.sh` never trusts an unknown host |

## Running Docker commands by hand

`docker compose` commands must run from `/srv/dixie-detail`, or they fail with "no configuration file provided". Container names work from anywhere, for example `docker stop dixie-cloudflared-1`.
