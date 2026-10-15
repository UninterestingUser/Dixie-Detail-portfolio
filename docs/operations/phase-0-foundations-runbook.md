---
title: Phase 0 foundations runbook
summary: The step-by-step procedure that built the server foundation in Phase 0, with every correction found along the way, usable to rebuild the server from scratch.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-14
tags: [operations, runbook, phase-0, rebuild]
related: [docs/architecture/server-and-stack.md, docs/architecture/secrets.md, docs/operations/troubleshooting.md, docs/operations/deploying-changes.md, docs/operations/workstation-setup.md]
---

# Phase 0 foundations runbook

Phase 0 ended on 2026-10-13 with the server running the empty stack, reachable privately over Tailscale and publicly through the Cloudflare Tunnel, backed up nightly to the RAID and Google Drive, and watched by Healthchecks.io. The restore test was deferred until the database had tables, and passed on 2026-10-14, which completed Phase 0.

This runbook is the procedure as finally executed, with every correction folded in. It was first written as the Claude doc "Phase 0: Foundations runbook" (now frozen). To rebuild the server, follow it in order; each step ends with a check. Problems met along the way are in [troubleshooting.md](troubleshooting.md).

## Who does what

The owner handles accounts, keys and anything that needs a sign-in or hands on the server. Claude Code, running in the project folder on the Fedora workstation, writes the code and configuration into the repository. The server pulls from GitHub and runs it.

## Step 1: Repository and workstation

Set up the workstation and create the private repository as in [workstation-setup.md](workstation-setup.md). Then ask Claude Code: "Read CLAUDE.md and docs/overview/roadmap.md. Create a GitHub milestone for each phase and an issue for each Phase 0 task, using gh."

**Check:** the repository shows as Private on GitHub, and the Phase 0 milestone lists its issues.

## Step 2: Prepare the server

Run over SSH on the server.

**Updates, clock and tools.** Security updates install themselves from then on.

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y unattended-upgrades apcupsd git jq libtss2-rc0t64
sudo dpkg-reconfigure -plow unattended-upgrades
sudo timedatectl set-timezone America/New_York
docker compose version
```

If `docker compose version` fails, install Docker's official packages from its Ubuntu install guide.

**Battery shutdown.** In `/etc/apcupsd/apcupsd.conf` set these lines; remove anything after `DEVICE` (such as `/dev/ttyS0`), because the unit is connected by USB:

```
UPSCABLE usb
UPSTYPE usb
DEVICE
BATTERYLEVEL 20
MINUTES 5
```

Then `sudo systemctl restart apcupsd` (restart, because the package already started it with the defaults) and `apcaccess status`, which should show `STATUS : ONLINE`, `MBATTCHG : 20 Percent` and `MINTIMEL : 5 Minutes`.

**Folders.**

```bash
sudo mkdir -p /srv/dixie-detail /mnt/raid/Backups/dixie-detail
sudo chown $USER: /srv/dixie-detail /mnt/raid/Backups/dixie-detail
```

**Bitwarden.**

1. In Secrets Manager, create the project `Dixie Detail` and the machine account `dixie-server` with read access to it, then create an access token. Bitwarden shows it once.
2. Install the `bws` command from the Linux download in Bitwarden's Secrets Manager CLI guide.
3. Run `systemd-analyze has-tpm2`. The first line must say `yes`. If it says `no`, enable AMD fTPM in the BIOS; if `partial`, a line starting with `-` names the missing piece.
4. Store the token encrypted, one line at a time; after `read -rs BWS_TOKEN`, paste the token and press Enter:

```bash
sudo mkdir -p /etc/credstore.encrypted
read -rs BWS_TOKEN
printf '%s' "$BWS_TOKEN" | sudo systemd-creds encrypt --with-key=host+tpm2 --name=bws-token - /etc/credstore.encrypted/dixie-bws-token.cred
unset BWS_TOKEN
```

Check: `sudo systemd-creds decrypt --name=bws-token /etc/credstore.encrypted/dixie-bws-token.cred - | wc -c` prints the token's length.

**Deploy key.** Made in memory, kept in Bitwarden, never saved to disk:

```bash
ssh-keygen -t ed25519 -f /dev/shm/dixie_deploy -N "" -C "Server deploy key"
cat /dev/shm/dixie_deploy.pub
cat /dev/shm/dixie_deploy
```

Add the `.pub` line under the repository's Settings › Deploy keys with "Allow write access" off. Save the private key, every line, as the Bitwarden secret `DEPLOY_SSH_KEY`, the name `ops/deploy.sh` asks for. (Phase 0 named it `DEPLOY_KEY`, which had to be renamed.) Then `rm /dev/shm/dixie_deploy /dev/shm/dixie_deploy.pub`.

**First clone,** one line at a time:

```bash
export BWS_ACCESS_TOKEN="$(sudo systemd-creds decrypt --name=bws-token /etc/credstore.encrypted/dixie-bws-token.cred -)"
eval "$(ssh-agent -s)"
bws secret list | jq -r '.[] | select(.key=="DEPLOY_SSH_KEY") | .value' | ssh-add -
git clone git@github.com:OWNER/Dixie-Detail.git /srv/dixie-detail
ssh-agent -k
unset BWS_ACCESS_TOKEN
```

Accept GitHub's host fingerprint `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` on first connection. No firewall changes are needed.

**Check:** `apcaccess status` shows ONLINE, `/srv/dixie-detail` holds the repository, and `ls ~/.ssh` shows no deploy key.

## Step 3: The Docker stack

1. Claude Code built the stack from this request: compose.yaml with PostgreSQL, a minimal Django app with a `/health` page, Caddy and cloudflared; Caddy serving the whole app on `127.0.0.1:8000` and only `/health` and `/api/public/` on port 8080 inside the Docker network; no other published ports; a `dixie-stack.service` unit loading the Bitwarden token with `LoadCredentialEncrypted=` and passing secrets to containers only as in-memory files; `ops/deploy.sh`; non-secret settings in `.env`; code at `/srv/dixie-detail`.
2. Merge the pull request.
3. In Bitwarden, add the secrets the start script needs, named exactly as the code asks (the command is in step 4 of [deploying-changes.md](deploying-changes.md)): in Phase 0, `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY` and `CLOUDFLARE_TUNNEL_TOKEN`. The tunnel token comes from step 4, item 1, which therefore happens first. Use Bitwarden's generator for passwords.
4. Pull on the server ([deploying-changes.md](deploying-changes.md)).
5. Create `.env`: `cp .env.example .env`, then set `BWS_PROJECT_ID` (copy the ID from the end of the Bitwarden project page's address), `BWS_SERVER_URL=https://vault.bitwarden.com`, and `DJANGO_ALLOWED_HOSTS` (step 5).
6. Install and start the stack:

```bash
cd /srv/dixie-detail
sudo cp ops/dixie-stack.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dixie-stack
docker compose ps
curl http://127.0.0.1:8000/health
```

**Check:** the health page answers on the server, and `http://192.0.2.10:8000/health` from another computer on the LAN fails to connect.

## Step 4: The Cloudflare Tunnel

1. In the Cloudflare dashboard, Networking › Tunnels (under Zero Trust on some dashboards), create a Cloudflared tunnel named `dixie-detail`. On the install page choose Docker, copy only the long string after `--token`, and save it as the Bitwarden secret `CLOUDFLARE_TUNNEL_TOKEN`. Do not run Cloudflare's command; the stack has its own connector.
2. Restart the stack (`sudo systemctl restart dixie-stack`) and wait for the tunnel to show Healthy.
3. On the tunnel's Routes tab, add a published application: subdomain `api`, domain `dixiedetail.com`, service URL `http://caddy:8080`. Never point it at the LAN address or `localhost`, which would expose other services on the server.

**Check:** with Wi-Fi off on a phone, `https://api.dixiedetail.com/health` answers and `https://api.dixiedetail.com/admin` returns "not found".

## Step 5: The control app on the tailnet

```bash
sudo tailscale serve --bg 8000
tailscale serve status
```

Add the tailnet host name to `DJANGO_ALLOWED_HOSTS` in `.env`, as a bare name, together with the others: `server.example-tailnet.ts.net,api.dixiedetail.com,127.0.0.1,localhost`. Then `sudo systemctl restart dixie-stack`.

**Check:** with Tailscale on, `https://server.example-tailnet.ts.net/health` opens on the phone and the Fedora machine; with Tailscale off on the phone, it does not.

## Step 6: Backups

1. Connect the server to Google Drive: `sudo apt install -y rclone restic`, then `rclone config`, new remote `gdrive`, type Google Drive; press Enter to leave client_id, client_secret and service_account_file blank; scope "Access to files created by rclone only"; No to advanced config; No to auto config. Run the `rclone authorize "drive" …` command it prints on the Fedora machine, sign in with the business account and paste the result back. No to Shared Drive. Then choose "Set configuration password", generate one in Bitwarden, save it as `RCLONE_CONFIG_PASS`, and enter it. Check with `rclone lsd gdrive:` (note the colon).
2. Generate the backup password in Bitwarden and save it as `RESTIC_PASSWORD`. Also keep a copy in the Bitwarden password vault, and a sealed paper copy stored away from the server.
3. Claude Code built the backups from this request: dump PostgreSQL to `/mnt/raid/Backups/dixie-detail` (14 daily, 12 monthly), send the dumps with restic to `rclone:gdrive:dixie-detail-backups`, load the Bitwarden token like `dixie-stack.service` and fetch the two passwords only while running, a service and 2:30 AM timer, a restore-test script, and Healthchecks pings.
4. Merge, pull, add the new settings to `.env` (`BACKUP_DIR=/mnt/raid/Backups/dixie-detail`, `RESTIC_REPOSITORY=rclone:gdrive:dixie-detail-backups` and `RCLONE_CONFIG`, the path to the rclone config), and create the restic repository once (see [backups-and-restore.md](backups-and-restore.md)).
5. Install the units and run a backup:

```bash
sudo cp ops/dixie-backup.service ops/dixie-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dixie-backup.timer
sudo systemctl start dixie-backup.service
```

6. Run `sudo ops/restore-test.sh`. (Deferred at the end of Phase 0 until the database had tables; passed on 2026-10-14.)

**Check:** a `dixie-detail-backups` folder appears in Google Drive, `systemctl list-timers | grep dixie` shows tonight's run, and the restore test passes.

## Step 7: Outside monitoring

1. Create a free Healthchecks.io account with the business email and add two checks: nightly backup (daily, 2 hours' grace) and public address (every 10 minutes, 5 minutes' grace).
2. Save both ping addresses as Bitwarden secrets, named as the scripts expect: `HEALTHCHECKS_BACKUP_URL` and `HEALTHCHECKS_PUBLIC_URL`.
3. Claude Code added a 10-minute timer that fetches the public health address and pings Healthchecks on success.
4. Merge, pull, add `PUBLIC_HEALTH_URL=https://api.dixiedetail.com/health` to `.env`, and install both `dixie-public-health.service` and `dixie-public-health.timer`.

**Check:** both checks are green. Stop the tunnel with `docker stop dixie-cloudflared-1`, wait about 15 minutes for the alert email, then `docker start dixie-cloudflared-1`.

## Done check

- [x] The repository is private and the server pulls with its read-only key.
- [x] `apcaccess status` shows the battery unit ONLINE.
- [x] `https://api.dixiedetail.com/health` answers from outside, and other paths return "not found".
- [x] The tailnet address opens the app with Tailscale on, and nothing answers on `192.0.2.10:8000`.
- [x] A backup has reached Google Drive and been restored: the restore test passed on 2026-10-14.
- [x] `RESTIC_PASSWORD` is in Secrets Manager, the Bitwarden vault and on sealed paper.
- [x] Both Healthchecks.io checks are green, and the test alert arrived.
- [x] No secret sits in plaintext on the server: `.env` holds only settings, `~/.ssh` has no deploy key, and rclone's config is encrypted.

## Sources

- [Cloudflare: create a remotely managed tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Bitwarden Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli)
- [systemd-creds](https://man7.org/linux/man-pages/man1/systemd-creds.1.html)
- [Healthchecks.io pricing](https://healthchecks.io/pricing)
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)
