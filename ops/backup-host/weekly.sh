#!/usr/bin/env bash
# The backup host's weekly job (decision 0127), run by
# dixie-backup-host-weekly.service:
# 1. prune the backup server's repository, which the production host can't
#    (append-only): keep 48 hourly, 14 daily and 12 monthly snapshots, for
#    the dumps and the photos each on their own;
# 2. check the repository's structure and read back 5% of its data;
# 3. run the restore test from it (ops/restore-test.sh --repo local).
# The repository is read straight from the RAID, as rest-server's own user.
# Pings HEALTHCHECKS_BACKUP_HOST_URL (start, then success, or failure with
# the end of the log). Both secrets come from the host's own credentials
# (decision 0126).
set -euo pipefail

cd "$(dirname "$0")/../.."
# shellcheck source=../lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=../lib/restic.sh
. ops/lib/restic.sh
# shellcheck source=../lib/healthchecks.sh
. ops/lib/healthchecks.sh
# shellcheck source=../lib/errors.sh
. ops/lib/errors.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-backup-host-weekly.service}"
KEEP_HOURLY=48
KEEP_DAILY=14
KEEP_MONTHLY=12
PING_BODY_BYTES=10000

hc_url=$(host_credential healthchecks-backup-host-url) || hc_url=""
restic_password=$(host_credential restic-password)
restic_settings_from_env_file
restic_use local

weekly() {
	echo "Pruning the backup server's repository: $KEEP_HOURLY hourly, $KEEP_DAILY daily, $KEEP_MONTHLY monthly"
	run_restic forget --host "$RESTIC_HOST" --group-by host,paths \
		--keep-hourly "$KEEP_HOURLY" --keep-daily "$KEEP_DAILY" --keep-monthly "$KEEP_MONTHLY" --prune --retry-lock 30m
	echo "Checking the repository"
	run_restic check --read-data-subset 5% --retry-lock 30m
	ops/restore-test.sh --repo local
}

log="$RUNTIME_DIRECTORY/weekly.log"
hc_ping "$hc_url" /start
set +e
(set -e; report_failures backup-host-weekly; weekly) 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e
if ((rc == 0)); then
	hc_ping "$hc_url" ""
else
	echo "backup-host-weekly: failed with exit status $rc" | tee -a "$log" >&2
	tail -c "$PING_BODY_BYTES" -- "$log" >"$log.tail"
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
