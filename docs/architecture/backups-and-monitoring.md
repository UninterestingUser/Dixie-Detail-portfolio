---
title: Backups and monitoring design
summary: How the database is backed up every night to the RAID and to Google Drive, how long copies are kept, and how Healthchecks.io watches the backups and the public path.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-18
tags: [backups, restic, rclone, monitoring, healthchecks]
related: [docs/operations/backups-and-restore.md, docs/operations/monitoring.md, docs/decisions/0027-backups-to-google-drive.md, docs/decisions/0039-healthchecks-monitoring.md]
---

# Backups and monitoring design

The database is the business, so it is copied every night to two places. The RAID survives a failed disk; the off-site copy covers a mistake, corruption, fire or theft.

## What runs every night

`dixie-backup.timer` starts `dixie-backup.service` at 2:45 AM Eastern, between the public health check's 10-minute runs, so the two never call Bitwarden in the same minute ([decision 0070](../decisions/0070-nightly-backup-at-2-45.md)). On the Sunday clocks spring forward, 2:45 AM does not exist, so the timer runs the backup at 3:45 AM that day instead. A run missed while the server was off happens at the next boot. The service runs `ops/backup.sh`, which:

1. Dumps the PostgreSQL database from the running `db` container, in PostgreSQL's custom format, and reads the dump back with `pg_restore --list` before keeping it as `/mnt/raid/Backups/dixie-detail/daily/dixie-detail-YYYY-MM-DD.dump`. A failed dump leaves no partial file behind.
2. Keeps the first dump of each month as `/mnt/raid/Backups/dixie-detail/monthly/dixie-detail-YYYY-MM.dump`, a hard link to the daily file, so it takes no extra space.
3. Applies the retention policy on the RAID: the newest 14 daily and 12 monthly dumps.
4. Sends that night's dump with restic to the repository `rclone:gdrive:dixie-detail-backups`, which is a folder in the owner's Google Workspace Drive. Every snapshot holds one file named `/dixie-detail.dump`, under the host name `dixie-detail` and the tag `nightly`.
5. Applies the same policy in restic, 14 daily and 12 monthly snapshots, and prunes the rest. While there is less than 14 days of history, restic also keeps the oldest snapshot; that is expected.
6. Pings the backup check on Healthchecks.io when it starts, then on success, or on failure with the last part of the run's log.

The backup fetches `RESTIC_PASSWORD`, `RCLONE_CONFIG_PASS` and `HEALTHCHECKS_BACKUP_URL` from Bitwarden only while it runs. Without `HEALTHCHECKS_BACKUP_URL` the backup still runs, with no pings. If Bitwarden cannot be reached there is no ping address either, so the alert comes from Healthchecks noticing the missed run.

## Why Google Drive and how it is protected

- The owner already pays for Google Workspace storage, and the dumps are a few megabytes, so the off-site copy costs nothing extra. Backblaze B2 was considered and dropped.
- The rclone remote `gdrive` uses the scope "Access to files created by rclone only", so the server cannot see the rest of the owner's Drive.
- restic encrypts everything with `RESTIC_PASSWORD` before it leaves the house; Google stores only scrambled files.
- Secrets are not part of the backup. Bitwarden keeps them.

## Restore test

`sudo ops/restore-test.sh` restores the newest Drive snapshot into a throwaway PostgreSQL container and checks it. The test fails if the newest snapshot is more than 36 hours old, if `pg_restore` reports an error, if the number of tables restored differs from the number in the dump, or if Django's `django_migrations` table is missing. It prints each table's row count. The container has no network and keeps its data in memory, and the dump streams from restic straight into it, so no plaintext copy is written to disk. A restore is required at the end of Phase 0 and again before launch. At the end of Phase 0 the test was deferred because the database had no tables yet; it passed on 2026-10-14, once the Phase 1 data model had created them. See [../overview/roadmap.md](../overview/roadmap.md).

## Monitoring with Healthchecks.io

Healthchecks.io emails the owner when something stops checking in. The free plan covers 20 checks with no stated limit on business use; two are used. UptimeRobot was ruled out because its free plan has been non-commercial since October 2024.

| Check | Expected | Grace | What it catches |
| --- | --- | --- | --- |
| Nightly backup | Once a day | 2 hours | A backup that failed or never ran |
| Public address | Every 10 minutes | 5 minutes | The server, its power, the home internet, the tunnel or the app being down |

For the public check, `ops/public-health.sh` on the server itself fetches `https://api.dixiedetail.com/health` every 10 minutes, retrying twice within a run, and pings only when the page answers `{"status":"ok"}`. A Cloudflare error page therefore counts as down. That request goes out to Cloudflare and back in through the tunnel, so a success proves the whole public path works. When anything along it fails, the pings stop and Healthchecks emails the owner. The ping addresses are Bitwarden secrets.

## Hosting fallback

If outages recur (more than one a month during booking hours, or any over four hours), the same Docker stack can move to a cloud server for about $14 to $29 a month.
