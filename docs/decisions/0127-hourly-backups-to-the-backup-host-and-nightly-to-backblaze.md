---
id: 127
title: "Hourly backups to an append-only backup server on the backup host, and nightly to Backblaze B2"
summary: "Hourly backups go to an append-only rest-server on the backup host over pinned TLS, and nightly also to Backblaze B2; Google Drive is retired."
date: 2026-11-22
area: backups
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: [docs/decisions/0070-nightly-backup-at-2-45.md, docs/decisions/0089-backup-rides-out-a-slow-drive.md]
superseded_by: []
related: [docs/decisions/0126-the-backup-host-keeps-two-secrets-as-systemd-credentials.md, docs/decisions/0087-restic-never-writes-into-a-pipe.md, docs/decisions/0099-quote-requests-with-photos.md, docs/architecture/backups-and-monitoring.md, docs/operations/backups-and-restore.md, ops/backup.sh, ops/lib/restic.sh, ops/lib/b2.sh, ops/offsite-prune.sh, ops/restore.sh, ops/restore-test.sh, ops/backup-host/, tools/test-backup.sh, tools/test-backup-host.sh]
---

# 0127: Hourly backups to an append-only backup server on the backup host, and nightly to Backblaze B2

**Status:** accepted · **Date:** 2026-11-22 · **Area:** backups

## Context

A review found (findings H3 and L4):

- **One machine.** The backups, the RAID copy and the restore test all lived on the server they protect. A dead server, or anything with root on it, took the database and every local copy together.
- **A day's work at risk.** Backups ran once a night, so a failure in the afternoon lost every booking since 2:45 AM.
- **Plain dumps on the RAID.** Fourteen daily and twelve monthly unencrypted dumps sat on the RAID, readable by anything with root on a server that also runs unrelated software.
- **Google Drive was slow.** rclone's shared Google client was rate-limited often enough to need decision 0089's timeouts and retries.

Production moves to a dedicated host; the current server becomes the backup host.

## Decision

- **The backup server.** restic's `rest-server` runs in Docker on the backup host (`ops/backup-host/`): `--append-only`, `--private-repos`, a password (`BACKUP_REST_PASSWORD`, stored there only as a bcrypt hash, decision 0126), TLS with a self-signed certificate for the backup host's address that the production host's restic pins with `--cacert`, on `BACKUP_REST_PORT` (8443) of `BACKUP_HOST_ADDRESS` only, its data in `BACKUP_REST_DATA_DIR` on the RAID. Append-only means the production host can add snapshots but never delete or change one, so a compromised production host can't destroy the history.
- **Every hour,** at 5 past (`dixie-backup.timer`), `ops/backup.sh hourly` dumps the database, checks the dump with `pg_restore --list`, and sends it (tag `database`) and the quote request photo folder (tag `photos`) to the backup server. It pings `HEALTHCHECKS_BACKUP_URL`.
- **Every night at 2:45 AM** (`dixie-backup-offsite.timer`, the time decision 0070 chose), `ops/backup.sh nightly` does the same and then sends the same dump and the photos to Backblaze B2 through restic's S3-compatible backend (`B2_REPOSITORY`, with `B2_KEY_ID` and `B2_APPLICATION_KEY`; restic recommends S3 over its native B2 backend). It pings `HEALTHCHECKS_OFFSITE_URL` for the B2 part. Each destination is tried even if the other failed.
- **Nothing but restic reaches B2.** No file is uploaded outside restic. `ops/lib/b2.sh` lists the whole bucket through B2's S3 API and fails on any file that isn't one of restic's repository files, inside the repository's folder; the weekly B2 prune runs it.
- **No plain text in the repositories.** The B2 repository and the backup server's repository are created with `restic_init_labeled`, which swaps the first key for one labeled host `restic`, user `restic` (restic's `init` can't set them), since a key file's host and user labels are the only plain text in a repository.
- **Retries kept.** Each dump upload gets three attempts of at most 8 minutes, 5 and then 15 minutes apart; a photo upload one attempt. What waiting can't fix isn't retried: a wrong password, a refused rest-server password, a certificate restic won't trust, a refused B2 key. One run at a time: an hourly run that finds the nightly one running skips itself, and the nightly run waits up to an hour for an hourly one.
- **Retention.** The backup host prunes its repository weekly, reading it straight from the RAID as rest-server's own user: 48 hourly, 14 daily and 12 monthly snapshots (`ops/backup-host/weekly.sh`). The production host prunes B2 weekly: 14 daily and 12 monthly (`ops/offsite-prune.sh`). Both group by host and path, so the dumps and the photos are kept each on their own, and the history copied from Drive joins the same timeline. B2 keeps prior versions of every file for 30 days (a bucket lifecycle rule), so a bad prune can be undone for a month.
- **The weekly restore test** runs on the backup host after the prune (`dixie-backup-host-weekly.timer`, Sunday 3:30 AM): a structure check, 5% of the data read back, and `ops/restore-test.sh --repo local`, which restores the newest dump into a throwaway PostgreSQL container and counts the photos as before. It pings `HEALTHCHECKS_BACKUP_HOST_URL`. `--repo b2` tests the B2 copy.
- **Local copies.** The production host keeps only its latest dump (`BACKUP_DIR/dixie-detail-latest.dump`). The backup host keeps no unencrypted dump; the old RAID dumps and photo mirror are deleted after the move.
- **Restoring production** is `ops/restore.sh`: the newest dump and photo snapshot, from the backup server, B2 (`--from b2`) or the backup host's own disk (`--from local`), into a fresh stack. It refuses a database that already has customers or users unless given `--over-existing-data`.
- **Google Drive is retired.** A one-time `restic copy` brings the Drive history into the backup server's repository; then the rclone remote, its config and `RCLONE_CONFIG_PASS` are deleted, and rclone stays out of the scripts.

## Alternatives considered

- **Keep Google Drive as the off-site copy.** It cost nothing extra but needed rclone, its shared Google client and decision 0089's workarounds. B2 speaks S3, which restic supports directly.
- **restic's native B2 backend.** restic's documentation recommends the S3-compatible API instead.
- **B2 Object Lock instead of versions.** Locked files can't be pruned until the lock ends, which fights the weekly prune. The 30-day prior versions cover a bad prune; Object Lock can be added later.
- **Hourly to B2 as well.** 24 times the transactions for a copy whose job is surviving a fire or theft; the backup server covers the hours.
- **rsync of the dumps to the backup host.** Plain dumps on the backup host were finding L4; restic encrypts.

## Consequences

- The worst-case loss falls from about a day to about an hour, and a dead production host no longer takes the backups with it.
- The backup host must be up for the hourly backups; when it's down they fail and Healthchecks says so, while the nightly B2 copy goes on.
- B2 costs a little each month; the repository is small.
- `RESTIC_PASSWORD` opens all three copies; its paper copy (decision 0041) matters more than ever.
- Decision 0070's 2:45 AM time stands for the nightly run; decision 0089's Drive-specific settings (rclone's timeout and call limit) are gone, its retries stay.
