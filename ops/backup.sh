#!/usr/bin/env bash
# The backups (decision 0127). Run on the production host by
#   dixie-backup.service, every hour at 5 past:   backup.sh hourly
#   dixie-backup-offsite.service, at 2:45 AM:      backup.sh nightly
#
# Both runs:
# 1. Dump PostgreSQL from the running db container, read the dump back with
#    pg_restore --list, and keep it as $BACKUP_DIR/dixie-detail-latest.dump,
#    replacing the last one: the production host keeps only its latest
#    local dump.
# 2. Send the dump (tag database) and then the quote request photo folder
#    (tag photos) to the backup server's repository: the backup host's
#    rest-server, append-only, so this host can add snapshots but never
#    delete one. Its ping is HEALTHCHECKS_BACKUP_URL.
# The nightly run then sends the same dump and the photos to Backblaze B2
# (restic's S3 backend), pinging HEALTHCHECKS_OFFSITE_URL. Nothing reaches
# B2 except restic's encrypted repository. Each destination is tried even if
# the other failed, and has its own ping; a failure in either fails the run.
# Nothing is pruned here: the backup host prunes its repository itself, and
# dixie-offsite-prune.timer prunes B2 weekly.
#
# Each dump upload gets up to three attempts of at most 8 minutes, 5 and
# then 15 minutes apart (decision 0089); a photo upload gets one attempt,
# and the next run sends whatever was missed. The database dump is never
# retried, nor is what waiting can't fix: a wrong password, a missing
# repository, a refused certificate or key. Worst case for one destination:
# about 56 minutes. An hourly run that finds the nightly one running skips
# itself (the nightly run backs up that hour); the nightly run waits up to
# an hour for an hourly one to end. Worst case for the nightly run: about
# 2 h 55 min, inside its unit's TimeoutStartSec.
#
# The secrets come from Bitwarden at the start of the run and live only in
# this script's memory and in restic's environment.
set -euo pipefail

mode=${1:-hourly}
[[ $mode == hourly || $mode == nightly ]] || { echo "backup: usage: backup.sh hourly|nightly" >&2; exit 2; }

cd "$(dirname "$0")/.."
# shellcheck source=lib/hold.sh
. ops/lib/hold.sh
held_skip backup
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh
# shellcheck source=lib/errors.sh
. ops/lib/errors.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-backup.service or dixie-backup-offsite.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"
: "${BACKUP_DIR:?set BACKUP_DIR in .env}"
: "${POSTGRES_DB:?set POSTGRES_DB in .env}" "${POSTGRES_USER:?set POSTGRES_USER in .env}"
# The quote request photos (decision 0099), mounted into the app container.
QUOTE_PHOTO_HOST_DIR=${QUOTE_PHOTO_HOST_DIR:-/srv/dixie-quote-photos}
# One run at a time: the hourly and the nightly run share this lock.
BACKUP_LOCK=${BACKUP_LOCK:-/run/dixie-backup.lock}

SNAPSHOT_FILE=dixie-detail.dump
# Minutes to wait before the second and the third attempt of a dump upload.
RETRY_WAITS=(5 15)
# Longest a single restic attempt may run (see run_restic).
ATTEMPT_LIMIT=8m
# Most bytes sent with a failure ping, as the ops scripts always have.
PING_BODY_BYTES=10000

exec 9>"$BACKUP_LOCK"
if [[ $mode == hourly ]]; then
	if ! flock -n 9; then
		echo "backup: the nightly run is in progress and backs up this hour; this hourly run is skipped"
		exit 0
	fi
else
	flock -w 3600 9 || { echo "backup: an hourly run held the lock for an hour; giving up" >&2; exit 1; }
fi

# If this fails there is no ping URL either; Healthchecks reports the
# missing ping when the grace time runs out. One Bitwarden call for all.
targets=(backup-server)
[[ $mode == hourly ]] || targets+=(b2)
bws_load "$BWS_PROJECT_ID"
hc_backup=$(bws_get_optional HEALTHCHECKS_BACKUP_URL)
hc_offsite=$(bws_get_optional HEALTHCHECKS_OFFSITE_URL)
# Reuses the fetch above, then drops it.
restic_load_secrets "$BWS_PROJECT_ID" "${targets[@]}" ||
	{ echo "backup: couldn't read the secrets from Bitwarden" >&2; exit 1; }

dump="$BACKUP_DIR/dixie-detail-latest.dump"

# make_dump: dumps the database to $dump, once per run.
make_dump() {
	[[ ! -e $RUNTIME_DIRECTORY/dumped ]] || return 0
	install -d -m 0700 "$BACKUP_DIR"
	local partial="$dump.partial"
	echo "Dumping $POSTGRES_DB to $dump"
	# Read the archive back before trusting it.
	if ! docker compose exec -T db pg_dump --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB" >"$partial" ||
		! docker compose exec -T db pg_restore --list <"$partial" >/dev/null; then
		rm -f -- "$partial"
		echo "backup: the database dump failed" >&2
		return 1
	fi
	mv -f -- "$partial" "$dump"
	touch "$RUNTIME_DIRECTORY/dumped"
}

# not_retried: true when restic's last error is one waiting can't fix.
not_retried() {
	(($1 == 10 || $1 == 12)) ||
		grep -qiE 'wrong password or no key found|401 Unauthorized|x509:|certificate|InvalidAccessKeyId|SignatureDoesNotMatch|AccessDenied' <<<"$restic_last_error"
}

# restic_step NAME [--tries N] [--input FILE] RESTIC_ARGS...
# Runs a restic command through run_restic, retrying it as described at the
# top. N, if given, is the most attempts (default: one more than the number
# of waits). FILE, if given, is restic's stdin, opened afresh for every
# attempt. Logs each attempt; each failed one is also added, with restic's
# last error lines, to $attempts_log for the failure ping.
restic_step() {
	local name=$1 input=/dev/null attempt=1 rc wait
	local tries=$((${#RETRY_WAITS[@]} + 1)) restic_time_limit=$ATTEMPT_LIMIT
	shift
	if [[ $1 == --tries ]]; then
		tries=$2
		shift 2
	fi
	if [[ $1 == --input ]]; then
		input=$2
		shift 2
	fi
	while :; do
		echo "backup: $name, attempt $attempt of $tries, at $(TZ=America/New_York date '+%H:%M:%S %Z')"
		rc=0
		run_restic "$@" <"$input" || rc=$?
		if ((rc == 0)); then
			((attempt == 1)) || echo "backup: $name succeeded on attempt $attempt of $tries"
			return 0
		fi
		echo "backup: $name, attempt $attempt of $tries, failed with exit status $rc$(restic_status_meaning "$rc")" >&2
		{
			echo "== $name, attempt $attempt of $tries, $(TZ=America/New_York date '+%F %H:%M:%S %Z'): exit status $rc$(restic_status_meaning "$rc")"
			printf '%s\n' "$restic_last_error"
		} >>"$attempts_log"
		if not_retried "$rc"; then
			echo "backup: waiting will not fix this, so $name is not retried" >&2
			return "$rc"
		fi
		if ((attempt == tries)); then
			echo "backup: $name failed $tries times; giving up" >&2
			return "$rc"
		fi
		wait=${RETRY_WAITS[attempt - 1]}
		echo "backup: trying $name again in $wait minutes" >&2
		sleep "$((wait * 60))"
		attempt=$((attempt + 1))
	done
}

# restic_status_meaning STATUS: what a restic exit status means, for the log.
restic_status_meaning() {
	case $1 in
		10) echo " (the repository does not exist)" ;;
		11) echo " (the repository is locked)" ;;
		12) echo " (wrong password)" ;;
		124 | 137) echo " (ran longer than $ATTEMPT_LIMIT and was stopped)" ;;
		130) echo " (interrupted)" ;;
	esac
}

# send_to TARGET: the dump, then the photo folder, to one repository.
send_to() {
	make_dump
	# ops/deploy.sh creates the photo folder, owned by the app's user.
	[[ -d $QUOTE_PHOTO_HOST_DIR ]] || { echo "backup: $QUOTE_PHOTO_HOST_DIR is missing; run ops/deploy.sh" >&2; return 1; }
	restic_use "$1"
	echo "Sending the dump and $(find "$QUOTE_PHOTO_HOST_DIR" -type f -name '*.jpg' | wc -l) quote request photo(s) to $1"
	restic_step "upload to $1" --input "$dump" \
		backup --host "$RESTIC_HOST" --tag database --stdin --stdin-filename "$SNAPSHOT_FILE"
	restic_step "photo upload to $1" --tries 1 \
		backup --host "$RESTIC_HOST" --tag photos "$QUOTE_PHOTO_HOST_DIR"
}

# part NAME PING_URL TARGET: sends to TARGET with its own log and pings.
# Called with set +e (see the end of this script).
part() {
	local name=$1 url=$2 target=$3 rc room
	log="$RUNTIME_DIRECTORY/$name.log"
	attempts_log="$RUNTIME_DIRECTORY/$name-attempts.log"
	: >"$attempts_log"
	hc_ping "$url" /start
	(set -e; report_failures "backup ($name)"; send_to "$target") 2>&1 | tee "$log"
	rc=${PIPESTATUS[0]}
	if ((rc == 0)); then
		hc_ping "$url" ""
		return 0
	fi
	echo "backup: $name failed with exit status $rc" | tee -a "$log" >&2
	# Every failed attempt first, then as much of the end of the log as fits.
	{
		if [[ -s $attempts_log ]]; then
			echo "Failed restic attempts, each with restic's last error lines:"
			cat -- "$attempts_log"
			echo
			echo "End of the run's log:"
		fi
	} >"$log.tail"
	room=$((PING_BODY_BYTES - $(stat -c %s -- "$log.tail")))
	((room <= 0)) || tail -c "$room" -- "$log" >>"$log.tail"
	hc_ping "$url" /fail "$log.tail"
	return "$rc"
}

# Not `part ... || status=$?`: a call on the left of || runs with set -e
# off, even inside the subshell that turns it back on, so a failed upload
# would carry on. set +e here, and set -e in part's subshell, work.
rm -f -- "$RUNTIME_DIRECTORY/dumped"
set +e
part backup-server "$hc_backup" backup-server
status=$?
if [[ $mode == nightly ]]; then
	part offsite "$hc_offsite" b2
	rc=$?
	((status)) || status=$rc
fi
exit "$status"
