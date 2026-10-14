---
title: Running and checking backups, and restoring
summary: How to confirm the nightly backup ran, run one by hand, test a restore, and recover the database from the RAID or from Google Drive.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-13
tags: [operations, backups, restore, restic]
related: [docs/architecture/backups-and-monitoring.md, docs/architecture/secrets.md, docs/operations/troubleshooting.md]
---

# Running and checking backups, and restoring

The design is in [../architecture/backups-and-monitoring.md](../architecture/backups-and-monitoring.md). This page is the hands-on procedure.

## Confirm the nightly backup ran

- Healthchecks.io emails the owner if the nightly backup check misses its 2:30 AM run by more than 2 hours. No email means it ran.
- On the server, `systemctl list-timers | grep dixie-backup` shows the last and next run.
- `journalctl -u dixie-backup.service --no-pager | tail -20` shows the last run's output, ending with "snapshot … saved" and the retention summary.
- The `dixie-detail-backups` folder in Google Drive shows recent changes, and `/mnt/raid/Backups/dixie-detail/daily` holds today's dump.

## Run a backup by hand

```bash
sudo systemctl start dixie-backup.service
journalctl -u dixie-backup.service --no-pager | tail -15
```

## Test a restore

```bash
sudo /srv/dixie-detail/ops/restore-test.sh
```

The script restores the newest Drive snapshot into a throwaway PostgreSQL container with no network and its data in memory, then checks that the snapshot is under 36 hours old, that `pg_restore` finished without an error, that every table in the dump came back, and that `django_migrations` exists. It prints each table's row count and ends with `restore-test: PASS`. The container is removed either way. The test must pass at the end of Phase 0 and again before launch. It fails with "django_migrations is missing" until the database has tables; at the end of Phase 0 that was expected, and the test was deferred to Phase 1.

## Recover the database (outline)

A full recovery procedure will be written and rehearsed before launch, once the database holds real data. The outline:

1. Stop everything except the database: `cd /srv/dixie-detail && sudo docker compose stop app caddy cloudflared`. Leave `dixie-stack` itself running: the database container needs the secret files, which disappear when the unit stops.
2. Choose the copy: the newest dump in `/mnt/raid/Backups/dixie-detail/daily` if the RAID is fine, otherwise the newest restic snapshot from Google Drive.
3. For a Drive copy, `sudo /srv/dixie-detail/ops/restic.sh dump latest /dixie-detail.dump > /root/restore.dump`. The script fetches `RESTIC_PASSWORD` and `RCLONE_CONFIG_PASS` from Bitwarden for that one command. Delete the file when you are done.
4. Load the dump over the existing database: `sudo docker compose exec -T db pg_restore --clean --if-exists -U dixie -d dixie < /root/restore.dump`.
5. Start the full stack with `sudo systemctl restart dixie-stack` and check the app.

If the server itself is lost, rebuild it with [phase-0-foundations-runbook.md](phase-0-foundations-runbook.md), then restore from Google Drive. Without `RESTIC_PASSWORD` the Drive copy cannot be opened; copies are in Bitwarden Secrets Manager, the owner's Bitwarden vault and a sealed paper copy.

## First-time setup notes

- The restic repository was created once by hand with `restic -r rclone:gdrive:dixie-detail-backups init`; the backup script does not create it. On a rebuild, `sudo /srv/dixie-detail/ops/restic.sh init` does the same with the passwords fetched from Bitwarden.
- rclone's built-in Google client is shared by every rclone user and can be rate-limited. If Drive uploads start failing with quota errors, create an OAuth client in the business's Google Cloud project and enter its ID and secret in `rclone config`; the client secret then belongs in the encrypted rclone config only.
- The rclone remote `gdrive` was set up with `rclone config` under the owner's user account. The backup runs as root, so the `RCLONE_CONFIG` setting in `.env` points it at that encrypted config file.

## Other restic commands

`ops/restic.sh` runs any restic command against the Drive repository with the passwords fetched from Bitwarden for that one command:

| Task | Command |
| --- | --- |
| List the snapshots on Drive | `sudo /srv/dixie-detail/ops/restic.sh snapshots` |
| Check the repository's structure | `sudo /srv/dixie-detail/ops/restic.sh check` |
