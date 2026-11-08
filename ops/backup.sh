#!/usr/bin/env bash
# Nightly backup. Run by dixie-backup.service (dixie-backup.timer, 2:45 AM).
#
# 1. Dumps PostgreSQL from the running db container to
#    $BACKUP_DIR/daily/dixie-detail-YYYY-MM-DD.dump, and links the month's
#    first dump into $BACKUP_DIR/monthly/.
# 2. Keeps the newest 14 daily and 12 monthly dumps.
# 3. Mirrors the quote request photo folder ($QUOTE_PHOTO_HOST_DIR) to
#    $BACKUP_DIR/quote-photos/ (decision 0099).
# 4. Sends tonight's dump to the restic repository on Google Drive and
#    applies the same 14 daily / 12 monthly policy there, to the dumps
#    (tag nightly) and the photo snapshots (tag photos) each on their own.
# 5. Sends the photo folder to the same repository, tagged photos. restic
#    uploads only photos it has not stored before.
#
# Google Drive is sometimes slow or rate-limiting, so each restic step for
# the dump (the upload, then forget/prune) gets up to three attempts of at
# most 8 minutes each, 5 and then 15 minutes apart (decision 0089). The
# photo upload gets one attempt of at most 8 minutes: a night's new photos
# take seconds, a failure is reported like any other, and the next night
# sends whatever was missed. The database dump is never retried. A wrong
# password or a missing repository is not retried either: waiting cannot
# fix them. Worst case with every retry: about 1 h 52 min, inside the
# unit's TimeoutStartSec and the Healthchecks grace time (both 2 hours).
#
# RESTIC_PASSWORD and RCLONE_CONFIG_PASS come from Bitwarden at the start of
# the run and live only in this script's memory and in the environment of
# the restic and rclone processes it starts. Healthchecks gets a start ping,
# then a success or failure ping; the failure ping carries every failed
# restic attempt's error and the end of the run's log. A failure prints what
# failed (ops/lib/errors.sh), and a locked restic repository also names the unlock
# command (ops/lib/restic.sh), so both reach the failure ping's log.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh
# shellcheck source=lib/errors.sh
. ops/lib/errors.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-backup.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"
: "${BACKUP_DIR:?set BACKUP_DIR in .env}"
: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY in .env}"
: "${POSTGRES_DB:?set POSTGRES_DB in .env}" "${POSTGRES_USER:?set POSTGRES_USER in .env}"
# The quote request photos (decision 0099), mounted into the app container.
QUOTE_PHOTO_HOST_DIR=${QUOTE_PHOTO_HOST_DIR:-/srv/dixie-quote-photos}

KEEP_DAILY=14
KEEP_MONTHLY=12
SNAPSHOT_FILE=dixie-detail.dump
# Minutes to wait before the second and the third attempt of a restic step.
RETRY_WAITS=(5 15)
# Longest a single restic attempt may run (see run_restic).
ATTEMPT_LIMIT=8m
# Most bytes sent with the failure ping, as the ops scripts always have.
PING_BODY_BYTES=10000

# If this fails there is no ping URL either; Healthchecks reports the
# missing ping when the grace time runs out.
# One Bitwarden call for all three, retried if Bitwarden is rate-limiting.
bws_load "$BWS_PROJECT_ID"
restic_password=$(bws_get RESTIC_PASSWORD)
rclone_config_pass=$(bws_get RCLONE_CONFIG_PASS)
hc_url=$(bws_get_optional HEALTHCHECKS_BACKUP_URL)
bws_forget

# keep_newest DIR N: delete all but the newest N dumps in DIR. Names sort by date.
keep_newest() {
	local dumps=("$1"/dixie-detail-*.dump)
	[[ -e ${dumps[0]} ]] || return 0
	local excess=$((${#dumps[@]} - $2))
	((excess > 0)) || return 0
	echo "Removing ${excess} old dump(s) from $1"
	rm -f -- "${dumps[@]:0:excess}"
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
		if ((rc == 10 || rc == 12)) || grep -q 'wrong password or no key found' <<<"$restic_last_error"; then
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

backup() {
	mountpoint -q /mnt/raid || { echo "backup: /mnt/raid is not mounted" >&2; return 1; }
	install -d -m 0700 "$BACKUP_DIR" "$BACKUP_DIR/daily" "$BACKUP_DIR/monthly"

	local day month daily monthly partial
	day=$(TZ=America/New_York date +%F)
	month=${day%-*}
	daily="$BACKUP_DIR/daily/dixie-detail-$day.dump"
	monthly="$BACKUP_DIR/monthly/dixie-detail-$month.dump"
	partial="$daily.partial"

	echo "Dumping $POSTGRES_DB to $daily"
	# Read the archive back before trusting it.
	if ! docker compose exec -T db pg_dump --format=custom -U "$POSTGRES_USER" -d "$POSTGRES_DB" >"$partial" ||
		! docker compose exec -T db pg_restore --list <"$partial" >/dev/null; then
		rm -f -- "$partial"
		echo "backup: the database dump failed" >&2
		return 1
	fi
	mv -f -- "$partial" "$daily"
	if [[ ! -e $monthly ]]; then
		echo "First dump of $month: keeping it as $monthly"
		ln -- "$daily" "$monthly"
	fi
	keep_newest "$BACKUP_DIR/daily" "$KEEP_DAILY"
	keep_newest "$BACKUP_DIR/monthly" "$KEEP_MONTHLY"

	# ops/deploy.sh creates the photo folder, owned by the app's user.
	[[ -d $QUOTE_PHOTO_HOST_DIR ]] || { echo "backup: $QUOTE_PHOTO_HOST_DIR is missing; run ops/deploy.sh" >&2; return 1; }
	echo "Copying $(find "$QUOTE_PHOTO_HOST_DIR" -type f -name '*.jpg' | wc -l) quote request photo(s) to $BACKUP_DIR/quote-photos"
	# Exit status 24 means a file vanished while rsync ran: a customer
	# removed a photo they had just picked. The copy is still good.
	rsync -a --delete -- "$QUOTE_PHOTO_HOST_DIR/" "$BACKUP_DIR/quote-photos/" || (($? == 24))

	echo "Sending to $RESTIC_REPOSITORY"
	restic_step upload --input "$daily" \
		backup --host "$RESTIC_HOST" --tag nightly --stdin --stdin-filename "$SNAPSHOT_FILE"
	# Two --tag options select either tag; --group-by keeps each its own group.
	restic_step forget/prune forget --host "$RESTIC_HOST" --tag nightly --tag photos --group-by host,tags \
		--keep-daily "$KEEP_DAILY" --keep-monthly "$KEEP_MONTHLY" --prune
	restic_step "photo upload" --tries 1 \
		backup --host "$RESTIC_HOST" --tag photos "$QUOTE_PHOTO_HOST_DIR"
}

log="$RUNTIME_DIRECTORY/backup.log"
attempts_log="$RUNTIME_DIRECTORY/attempts.log"
: >"$attempts_log"
hc_ping "$hc_url" /start
set +e
(set -e; report_failures backup; backup) 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e

if ((rc == 0)); then
	hc_ping "$hc_url" ""
else
	echo "backup: failed with exit status $rc" | tee -a "$log" >&2
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
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
