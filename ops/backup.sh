#!/usr/bin/env bash
# Nightly backup. Run by dixie-backup.service (dixie-backup.timer, 2:30 AM).
#
# 1. Dumps PostgreSQL from the running db container to
#    $BACKUP_DIR/daily/dixie-detail-YYYY-MM-DD.dump, and links the month's
#    first dump into $BACKUP_DIR/monthly/.
# 2. Keeps the newest 14 daily and 12 monthly dumps.
# 3. Sends tonight's dump to the restic repository on Google Drive and
#    applies the same 14 daily / 12 monthly policy there.
#
# RESTIC_PASSWORD and RCLONE_CONFIG_PASS come from Bitwarden at the start of
# the run and live only in this script's memory and in the environment of
# the restic and rclone processes it starts. Healthchecks gets a start ping,
# then a success or failure ping.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-backup.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"
: "${BACKUP_DIR:?set BACKUP_DIR in .env}"
: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY in .env}"
: "${POSTGRES_DB:?set POSTGRES_DB in .env}" "${POSTGRES_USER:?set POSTGRES_USER in .env}"

KEEP_DAILY=14
KEEP_MONTHLY=12
SNAPSHOT_FILE=dixie-detail.dump

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

	echo "Sending to $RESTIC_REPOSITORY"
	run_restic backup --host "$RESTIC_HOST" --tag nightly --stdin --stdin-filename "$SNAPSHOT_FILE" <"$daily"
	run_restic forget --host "$RESTIC_HOST" --tag nightly --group-by host,tags \
		--keep-daily "$KEEP_DAILY" --keep-monthly "$KEEP_MONTHLY" --prune
}

log="$RUNTIME_DIRECTORY/backup.log"
hc_ping "$hc_url" /start
set +e
(set -e; backup) 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e

if ((rc == 0)); then
	hc_ping "$hc_url" ""
else
	echo "backup: failed with exit status $rc" | tee -a "$log" >&2
	tail -c 10000 "$log" >"$log.tail"
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
