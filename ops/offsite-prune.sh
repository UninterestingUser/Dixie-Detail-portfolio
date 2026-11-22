#!/usr/bin/env bash
# Weekly, on the production host: prunes the Backblaze B2 repository to 14
# daily and 12 monthly snapshots, for the dumps and the photos each on their
# own, and checks that the bucket holds only restic's repository files
# (decision 0127). The backup host prunes the backup server's repository
# itself, since append-only stops this host from deleting anything there.
# B2 keeps prior versions of every file for 30 days, so a bad prune can be
# undone for a month. Run by dixie-offsite-prune.service; a failure pings
# HEALTHCHECKS_OFFSITE_URL's /fail with the end of the log.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh
# shellcheck source=lib/b2.sh
. ops/lib/b2.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh
# shellcheck source=lib/errors.sh
. ops/lib/errors.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-offsite-prune.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"
KEEP_DAILY=14
KEEP_MONTHLY=12
PING_BODY_BYTES=10000

bws_load "$BWS_PROJECT_ID"
hc_url=$(bws_get_optional HEALTHCHECKS_OFFSITE_URL)
restic_load_secrets "$BWS_PROJECT_ID" b2

prune() {
	restic_use b2
	# Grouped by paths, so the dumps and the photos are kept each on their
	# own, and the copied Drive history joins the same timeline.
	run_restic forget --host "$RESTIC_HOST" --group-by host,paths \
		--keep-daily "$KEEP_DAILY" --keep-monthly "$KEEP_MONTHLY" --prune --retry-lock 30m
	b2_check_only_repository_files
}

log="$RUNTIME_DIRECTORY/prune.log"
set +e
(set -e; report_failures offsite-prune; prune) 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e
if ((rc != 0)); then
	echo "offsite-prune: failed with exit status $rc" | tee -a "$log" >&2
	tail -c "$PING_BODY_BYTES" -- "$log" >"$log.tail"
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
