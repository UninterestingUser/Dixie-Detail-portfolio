---
id: 87
title: "restic never writes into a pipe, and the restore test downloads the snapshot into memory first"
summary: "The ops scripts send restic's output to a file or capture it whole, never into a pipe, so an early reader cannot cut restic off and leave a stale lock that stops the backups."
date: 2026-11-04
area: backups
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-04
supersedes: []
superseded_by: []
related: [docs/operations/troubleshooting.md, docs/operations/backups-and-restore.md, docs/decisions/0027-backups-to-google-drive.md, ops/lib/restic.sh, ops/lib/errors.sh, ops/restore-test.sh, tools/test-restic.sh]
---

# 0087: restic never writes into a pipe, and the restore test downloads the snapshot into memory first

**Status:** accepted · **Date:** 2026-11-04 · **Area:** backups

## Context

The restore test streamed `restic dump` straight into `pg_restore`, twice: once into `pg_restore --list` to count the tables, once into the restore itself. `pg_restore --list` reads only the archive's table of contents and stops reading. When restic still had data to write, it was killed by SIGPIPE, and with `pipefail` and `set -e` the script quit without a message after "Restoring into …". Whether it happened depended on timing, so the test failed only sometimes.

A restic that is killed does not remove its lock. The stale lock left on 2026-11-03 made every nightly backup fail at its `forget --prune` step until the owner ran `ops/restic.sh unlock` on 2026-11-04.

## Decision

1. **restic's output never goes into a pipe.** An ops script either captures it whole with `$(...)` and works on the captured text, or sends it to a file. `run_restic` in `ops/lib/restic.sh` says so, and `tools/test-restic.sh` fails if any ops script pipes it or runs restic around the helper.
2. **The restore test downloads the snapshot once** with `restic_dump` into a private folder in `/dev/shm`, in memory and readable only by root, and the throwaway PostgreSQL container reads it from a read-only mount. The folder is removed at the end, pass or fail, so no plaintext copy lands on disk, as before.
3. **A locked repository names the unlock command.** When restic cannot lock the repository, `run_restic` follows restic's own error with what to check (`pgrep -a restic`) and the command to run, `sudo /srv/dixie-detail/ops/restic.sh unlock`. The scripts do not unlock by themselves: a lock may belong to a restic that is still running.
4. **Every failure says what failed.** `restore-test.sh`, `backup.sh` and `gosu-test.sh` call `report_failures` from `ops/lib/errors.sh`, which prints the file, line, command and exit status of any failure that ends the script, and explains status 141 (cut off by SIGPIPE).

## Alternatives considered

- **Read the whole stream after `pg_restore --list`** (for example by piping its input through `tee` to `/dev/null`). It fixes this one command but keeps restic in a pipe, where the next early reader brings the problem back.
- **Count the tables from the restored database only.** That drops the check that every table in the dump came back, which is the point of the count.
- **Unlock automatically before each backup.** `restic unlock` removes only stale locks, but running it unasked hides the fact that something was cut off, and a lock from a restore test still running is real.
- **Run `restic dump --target FILE`.** It needs restic 0.17 or later; a shell redirect works with any version.

## Consequences

- The restore test downloads the snapshot once instead of twice, and holds it in memory while it runs, so the server needs free memory for one nightly dump, about the size of the files in `/mnt/raid/Backups/dixie-detail/daily`.
- A stale lock still needs a person, but the message says exactly what to run, in the terminal, the journal and the Healthchecks failure log.
- `tools/run-tests.sh` runs `tools/test-restic.sh`, which reproduces the 2026-11-03 failure with a fake restic.
