---
id: 89
title: "The nightly backup waits longer for Google Drive, retries each restic step twice, and calls Drive gently"
summary: "restic waits 5 minutes for rclone to open the Drive repository, each restic step of the backup gets three time-limited attempts, and rclone makes at most 5 Drive calls a second."
date: 2026-11-06
area: backups
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: [docs/decisions/0127-hourly-backups-to-the-backup-host-and-nightly-to-backblaze.md]
related: [docs/operations/backups-and-restore.md, docs/operations/troubleshooting.md, docs/architecture/backups-and-monitoring.md, docs/decisions/0027-backups-to-google-drive.md, docs/decisions/0087-restic-never-writes-into-a-pipe.md, ops/backup.sh, ops/lib/restic.sh, tools/test-restic.sh]
---

# 0089: The nightly backup waits longer for Google Drive, retries each restic step twice, and calls Drive gently

**Status:** superseded by [0127](0127-hourly-backups-to-the-backup-host-and-nightly-to-backblaze.md), which keeps the retries and drops the Drive settings · **Date:** 2026-11-06 · **Area:** backups

## Context

The nightly backups on 2026-10-31 and 2026-11-06 failed before uploading anything. restic starts rclone to reach the repository on Google Drive and, by default, waits 1 minute for it to open the repository; both nights Drive was slower than that. The 2026-11-05 run met Drive's rate limit several times and still finished. The RAID copy was made every night; only the off-site copy was missed.

The `gdrive` remote uses rclone's built-in Google client, which every rclone user in the world shares and which Google rate-limits as one app.

## Decision

1. **A 5-minute open timeout.** `run_restic` in `ops/lib/restic.sh` passes `-o rclone.timeout=5m` to every restic command, so the backup, the restore test and `ops/restic.sh` all get it.
2. **Each restic step of the backup is retried.** In `ops/backup.sh`, the upload and then `forget --prune` are separate steps. Each gets up to three attempts: the second after a 5-minute wait, the third after another 15 minutes. The upload reopens the dump file for every attempt. The database dump is never retried. Each attempt and its error are logged. A run that succeeds on a later attempt ends as a success; a run that fails sends the error of every failed attempt with the Healthchecks failure ping, ahead of the end of the run's log, within the 10,000 bytes the ops scripts send with a ping.
3. **No retry when waiting cannot help:** restic's exit status 12 (wrong password; also matched by its message "wrong password or no key found", which older restic versions give with status 1) and 10 (no repository). A locked repository (11) is retried, because the lock may belong to a restore test that is still running; a stale lock still needs `ops/restic.sh unlock` (decision 0087).
4. **Each attempt is time-limited** to 8 minutes. Then `timeout` sends SIGINT, on which restic removes its lock and stops, and SIGKILL a minute later if it is still running. Without a limit a hung attempt could run past the unit's limit, and systemd's SIGTERM at that point would come with no failure ping.
5. **At most 5 Drive calls a second.** restic hands its environment to the rclone it starts, so `run_restic` sets `RCLONE_TPSLIMIT=5` for restic only. restic's `-o rclone.args` is left alone: setting it replaces restic's whole default rclone command line (`serve restic --stdio …`).
6. **The worst case fits both 2-hour limits.** An attempt lasts at most 9 minutes (8 plus the minute before SIGKILL), so a step with every retry takes at most 3 × 9 + 5 + 15 = 47 minutes, and both steps 94 minutes. Add up to about 4 minutes for Bitwarden (three 65-second waits on a 429), about 1 minute for the database dump and up to about 1½ minutes for each Healthchecks ping (curl's 5 retries): about 1 hour 43 minutes from the unit's start, inside `TimeoutStartSec=2h`, and about 1 hour 38 minutes from the start ping to the last ping, inside the check's 2-hour grace time.
7. **The business's own Google OAuth client is documented, not made yet.** [backups-and-restore.md](../operations/backups-and-restore.md) has the procedure for moving the repository to it, including copying the repository, because a client with the "files created by rclone only" scope cannot see files made by another client. The client belongs in its own Google Cloud project with no billing account.

## Alternatives considered

- **Retry the whole backup, dump included.** The dump is local and has never failed; dumping again only adds time and a second file of the same night.
- **Let systemd restart the unit** (`Restart=on-failure`). Every restart would call Bitwarden and dump the database again, send a fresh start ping and a failure ping per try, and could not tell a wrong password from a slow Drive.
- **More attempts or longer waits.** With 8-minute attempts, a fourth attempt or a longer wait pushes the worst case past 2 hours. A night missed off-site is covered by the RAID copy and the alert.
- **restic's own `--retry-lock`.** It only covers a locked repository, not a slow Drive.
- **`--tpslimit` in `-o rclone.args`.** Replaces restic's default rclone arguments, so the arguments would have to be copied and kept in step with restic.
- **Full Drive access for a new client** (scope `drive`), so it could see the existing repository without copying it. The backup token could then read the whole business Drive, and the scope is restricted, so Google would show the unverified-app warning.

## Consequences

- A slow or rate-limited Drive delays the off-site copy by up to 20 minutes of waiting instead of failing it.
- When the upload attempt that timed out had in fact saved its snapshot, the retry saves another of the same night; the 14-daily policy keeps only the newest of the day.
- A failed run reports every attempt in the Healthchecks email, so it is clear whether Drive was slow every time or the problem was something else.
- `tools/test-restic.sh` runs `ops/backup.sh` against fakes of restic, bws, docker and curl to test the retries, the waits, the failure ping and the timeout option.
