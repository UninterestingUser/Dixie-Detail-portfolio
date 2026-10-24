---
title: Troubleshooting
summary: Known problems with the server, stack, backups and tools, each with the exact symptom, the cause and the fix, collected from Phase 0 onward.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-24
tags: [operations, troubleshooting, errors]
related: [docs/operations/deploying-changes.md, docs/operations/backups-and-restore.md, docs/architecture/server-and-stack.md, docs/architecture/secrets.md]
---

# Troubleshooting

Each entry gives the symptom as it appears on screen, the cause, and the fix. Add an entry whenever a new problem is solved; see [../CONVENTIONS.md](../CONVENTIONS.md).

## General habits that prevent most problems

- **Paste commands one line at a time** when any line asks for a password (`sudo`) or input (`read`). A prompt swallows the pasted lines after it, so they never run or are taken as the input.
- **After every pull,** compare `.env.example` with `.env` and install any new unit files. See [deploying-changes.md](deploying-changes.md).
- **Run `docker compose` from `/srv/dixie-detail`,** or use container names such as `dixie-app-1`.

## Stack and app

### "Bad Request (400)" from the health page or the tailnet address

**Cause:** the host name used is not in `DJANGO_ALLOWED_HOSTS`, or the setting contains `https://`, or the app was not restarted after `.env` changed.
**Fix:** set `DJANGO_ALLOWED_HOSTS=server.example-tailnet.ts.net,api.dixiedetail.com,127.0.0.1,localhost` (bare names, commas, no spaces), then `sudo systemctl restart dixie-stack`. Check the running value with `docker compose exec app printenv DJANGO_ALLOWED_HOSTS`. The restart recreates every container, so it should show the new value.

### The app logs "Control server error: [Errno 30] Read-only file system: '/home/app'" at every start

**Cause:** gunicorn 25.1 and later open a control socket for the `gunicornc` tool, by default under `$HOME/.gunicorn/`. The app container's file system is read-only and the `app` user has no home folder, so creating it fails. The app still served requests; only the control socket was missing.
**Fix (2026-10-14):** `app/Dockerfile` starts gunicorn with `--no-control-socket`, because nothing uses `gunicornc`: deploys restart the container instead. The file system stays read-only. Pointing the socket at the writable `/tmp` with `--control-socket /tmp/gunicorn.ctl` would also work. After the pull, `docker logs dixie-app-1` should show no control server error.

### dixie-stack fails with "Failed to load environment files: No such file or directory" (Result: resources)

**Cause:** the unit file points at a folder that does not exist. In Phase 0 it pointed at `/opt/dixie-detail` instead of `/srv/dixie-detail`.
**Fix:** correct the paths in the repository's unit file (decision 0042), pull, copy it to `/etc/systemd/system/`, `sudo systemctl daemon-reload`, `sudo systemctl restart dixie-stack`. Check with `grep -E '^(LoadCredential|EnvironmentFile|WorkingDirectory|ExecStart)' /etc/systemd/system/dixie-stack.service`.

### bws: "Profile has no `server_base` or `server_identity`"

**Cause:** the scripts run `bws` with a temporary settings profile that turns off its state file, and that profile has no server address unless `BWS_SERVER_URL` provides one. Since this was fixed, a missing setting stops the script earlier with "set BWS_SERVER_URL in .env".
**Fix:** put `BWS_SERVER_URL=https://vault.bitwarden.com` in `.env` (use `https://vault.bitwarden.eu` only for an EU Bitwarden account) and restart the stack.

### "429 Too Many Requests … Try again in 1m" from bws, and a script or the backup fails

**Symptom:** the nightly backup failed (Healthchecks alert, or `journalctl -u dixie-backup` shows the error), or another ops script stopped with `Error: Received error message from server: [429 Too Many Requests] Slow down! Too many requests. Try again in 1m.`
**Cause:** Bitwarden Secrets Manager limits how often one machine account may call it. Every ops script and unit uses the same machine account, so calls close together count against one limit. Until 2026-10-18 the backup timer (2:30 AM) fired in the same minute as the public health check, which runs every 10 minutes.
**Fix (2026-10-18):** `ops/lib/bws.sh` now fetches all of a run's secrets with one `bws secret list` call (`bws_load`), and on a 429 waits 65 seconds and tries again, up to 3 times. Each retry is logged as "bws: Bitwarden is rate-limiting this machine account (429 Too Many Requests); retry N of 3 in 65 seconds", so `journalctl -u dixie-backup` (or the unit concerned) shows how often it happens. `dixie-public-health.service` allows 6 minutes, enough for three waits, and the backup now runs at 2:45 AM, clear of the health check's 10-minute marks (decision 0070). If a run still fails after three retries, run it again by hand a few minutes later (`sudo systemctl start dixie-backup`) and check whether something else is calling Bitwarden in a loop. The helper's behavior is tested by `tools/test-bws.sh`.

### "jq: error … Bitwarden secret NAME: expected 1, found 0"

**Cause:** the code asks for a secret name that does not exist in the Dixie Detail project, usually a spelling or naming mismatch (Phase 0: the code wanted `POSTGRES_PASSWORD`, Bitwarden had `DB_PASSWORD`), or the secret is in a different project.
**Fix:** compare the names the scripts ask for (the command is in step 4 of [deploying-changes.md](deploying-changes.md)) with `bws secret list | jq -r '.[].key' | sort`, and rename the secret in Bitwarden.

### The stack will not start before step 4 of Phase 0

**Cause:** `ops/stack-start.sh` requires `CLOUDFLARE_TUNNEL_TOKEN`.
**Fix:** create the tunnel in Cloudflare and save its token in Bitwarden before the first start.

### `docker compose …` says "no configuration file provided: not found"

**Cause:** the command ran outside `/srv/dixie-detail`.
**Fix:** `cd /srv/dixie-detail` first, or use the container name with plain `docker`, such as `docker stop dixie-cloudflared-1`.

## Vehicle data import

### import_vehicle_data: "The download cache /srv/vehicle-data (setting VEHICLE_DATA_CACHE_DIR) is missing or cannot be written"

**Cause:** the one-off container was started without the cache folder mounted, or the host folder is not owned by the app container's user (uid 10001). The app container's own file system is read-only.
**Fix:** run `sudo /srv/dixie-detail/ops/deploy.sh`, which creates the host folder owned by uid 10001 when it is missing, or fix an existing folder's owner with `sudo chown 10001:10001 /srv/dixie-vehicle-data`. Start the command with `-v /srv/dixie-vehicle-data:/srv/vehicle-data`, as in [importing-vehicle-data.md](importing-vehicle-data.md). The monthly refresh mounts it itself.

### The vehicle import rejects rows from a make it was asked for

**Cause:** vPIC and the Canadian specifications match make names loosely and spell some differently. Found on 2026-10-22: asking vPIC for KTM also returns KTMMEX, asking for Indian also returns PERFORMANCE INDIAN, and the Canadian specifications call Ram "RAM TRUCKS", so every Ram row was rejected until `canada.make_names` mapped it.
**Fix:** check the rejected make. If it belongs, add it to the make's `vpic_names`, or for a Canadian spelling to `canada.make_names`, in [data/vehicle-data-import.yaml](../../data/vehicle-data-import.yaml), merge, deploy and run the import again. The cached files are reused, so nothing is downloaded again.

## systemd units and timers

### "Unit dixie-stack.service does not exist" or "cp: cannot stat 'ops/systemd/…'"

**Cause:** the unit file is somewhere other than the path in the instructions. In Phase 0 it was `ops/dixie-stack.service`.
**Fix:** `find /srv/dixie-detail -name "*.service" -not -path "*/.git/*"` and copy from the real path.

### `systemctl enable --now NAME.timer` says "Job failed"

**Cause:** the timer's matching `.service` file was not copied to `/etc/systemd/system/`.
**Fix:** copy the `.service` file, `sudo systemctl daemon-reload`, `sudo systemctl restart NAME.timer`.

### A timer is missing from `systemctl list-timers` after a deploy

**Cause:** until 2026-10-24, `ops/deploy.sh` ran to the end as the version from before its own pull, because bash keeps reading the file it opened. A pull that added a timer and its line in `deploy.sh` (as the monthly vehicle data refresh did) installed the timer's unit file but did not enable it. `deploy.sh` now starts its pulled copy after the pull, enables every timer in `ops/`, and ends with an error naming any timer that is not enabled and active.
**Fix:** run `sudo /srv/dixie-detail/ops/deploy.sh` again; the second run uses the new script. Or enable it by hand: `sudo systemctl enable --now NAME.timer`, then `systemctl list-timers | grep -i dixie`.

### A script stops with "set SETTING in .env" (for example `RESTIC_REPOSITORY` or `PUBLIC_HEALTH_URL`)

**Cause:** a pull added a setting to `.env.example` that the server's `.env` lacks.
**Fix:** run the `diff` command in [deploying-changes.md](deploying-changes.md) and add the missing lines. Phase 0 values: `RESTIC_REPOSITORY=rclone:gdrive:dixie-detail-backups`, `PUBLIC_HEALTH_URL=https://api.dixiedetail.com/health`.

## Backups

### restic: "repository does not exist: unable to open config file"

**Cause:** the restic repository on Google Drive has not been created; the backup script does not create it.
**Fix:** once: `sudo /srv/dixie-detail/ops/restic.sh init`. It fetches `RESTIC_PASSWORD` and `RCLONE_CONFIG_PASS` from Bitwarden for that one command and uses the rclone config named by `RCLONE_CONFIG` in `.env`.

### restore-test: "FAIL: django_migrations is missing" with "Tables: 0 in the dump"

**Cause:** the database is empty. The app already runs `python manage.py migrate --noinput` every time it starts, but the Phase 0 app has no models, and Django does not create its `django_migrations` table when there is nothing to migrate. Running `migrate` by hand changes nothing.
**Fix:** none needed in Phase 0. The test passes once Phase 1 adds the first models: the next start creates the tables, the next backup captures them, and the test can be re-run.

### restore-test: "FAIL: table count does not match" with twice as many tables in the dump as restored

The output reads, for example, "Tables: 126 in the dump, 63 restored", while the live database has 63 tables.

**Cause:** the script counted the dump's tables from `pg_restore --list`, which lists every table twice: once as `TABLE` (its definition) and once as `TABLE DATA` (its rows). The filter matched the word `TABLE` in the fourth field, which both kinds of entry have, so the expected count was doubled. The restore itself was fine. This first showed up on 2026-10-14, the first test run after the Phase 1 data model created the tables.
**Fix:** `ops/restore-test.sh` now counts only `TABLE` entries, skipping `TABLE DATA`. Pull the fix and run `sudo /srv/dixie-detail/ops/restore-test.sh` again; it should show the same number on both sides and end with `restore-test: PASS`.

### rclone: "gdrive" refers to a local folder / "directory not found"

**Cause:** the remote name was typed without its colon.
**Fix:** `rclone lsd gdrive:`. An empty list is normal: rclone sees only files it created.

### Checking that rclone's config is encrypted

`head -3 "$(rclone config file | tail -1)"` should show "# Encrypted rclone configuration File" and `RCLONE_ENCRYPT_V0:`. If it shows `[gdrive]` and a `token =` line, run `rclone config`, choose "Set configuration password" and use the `RCLONE_CONFIG_PASS` value.

## Secrets, keys and Git

### bws: "invalid value 'NAME' for '<SECRET_ID>'"

**Cause:** `bws secret get` takes a secret's ID, not its name.
**Fix:** look secrets up by name: `bws secret list | jq -r '.[] | select(.key=="NAME") | .value'`.

### ssh-add: "Error loading key "(stdin)": error in libcrypto"

**Cause:** nothing (or the wrong text) reached `ssh-add`, usually because the secret lookup failed.
**Fix:** check the `DEPLOY_SSH_KEY` secret's name and that it holds the whole private key, every line. Phase 0 stored the key as `DEPLOY_KEY`; it was renamed to `DEPLOY_SSH_KEY`, the name `ops/deploy.sh` asks for, on 2026-10-13.

### First pull asks "The authenticity of host 'github.com' can't be established"

**Cause:** normal on the first SSH connection. GitHub's ED25519 fingerprint is `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`.
**Fix:** type `yes` if the fingerprint matches.

### `systemd-analyze has-tpm2` says "partial" with "-libraries … -libtss2-rc.so.0"

**Cause:** the TPM works but a user-space library is missing. (`systemd-creds has-tpm2` is the older name of this command.)
**Fix:** `sudo apt install -y libtss2-rc0t64`, check again for `yes`, then re-encrypt the token with `--with-key=host+tpm2` (see [secrets-management.md](secrets-management.md)); a token encrypted before the fix used the host key only.

### `gh repo create` says "Unable to add remote origin"

**Cause:** the repository was created on GitHub, but the local folder already had a remote named `origin`; gh hides git's message.
**Fix:** `git remote set-url origin https://github.com/OWNER/Dixie-Detail.git` (or `git remote add …`), then `git push -u origin main`. Do not run `gh repo create` again.

## Server hardware and network

### apcaccess shows "STATUS : COMMLOST" with MBATTCHG 5 and MINTIMEL 3

**Cause:** apcupsd started when it was installed, before `apcupsd.conf` was edited; `enable --now` does not restart a running service. The 5% and 3-minute values are the defaults.
**Fix:** `sudo systemctl restart apcupsd`, wait 10 seconds, `apcaccess status`. The config must read `UPSCABLE usb`, `UPSTYPE usb` and a bare `DEVICE` line (remove `/dev/ttyS0`). If still COMMLOST, check `lsusb | grep -i "american power"` and the cable.

### The phone cannot open the tailnet address with Wi-Fi off

**Cause:** one of: the app returns 400 (allowed hosts), `tailscale serve` is not running, MagicDNS or HTTPS certificates are off, or the phone's Tailscale app is not using Tailscale DNS.
**Fix:** on the server, `curl http://127.0.0.1:8000/health`, `tailscale serve status`, `curl -sS https://server.example-tailnet.ts.net/health`. On the phone, open the `/health` page, turn on "Use Tailscale DNS", and set Android Private DNS to Automatic or Off while testing.
