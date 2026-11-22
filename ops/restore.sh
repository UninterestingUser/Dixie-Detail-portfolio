#!/usr/bin/env bash
# Restores production's database and quote request photos from the newest
# backup into a running, fresh stack (decision 0127). Run as root on the
# host that is to run production, with dixie-stack.service running:
#
#   sudo /srv/dixie-detail/ops/restore.sh                    # from the backup server
#   sudo /srv/dixie-detail/ops/restore.sh --from b2          # from Backblaze B2
#   sudo /srv/dixie-detail/ops/restore.sh --from local       # on the backup host, from its own disk
#
# Options: --snapshot ID picks a database snapshot other than the newest,
# --photo-snapshot ID a photo snapshot other than the newest, and
# --over-existing-data lets it replace a database that already has
# customers or users. Without that option it refuses: a fresh stack has
# only what its migrations create.
#
# It stops every container but the database, downloads the dump into a
# private folder in /dev/shm (in memory), loads it with pg_restore --clean
# in one transaction, writes the photos back to the photo folder, and
# restarts the stack, which runs the migrations a newer release needs. The
# download is removed at the end, pass or fail.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
SNAPSHOT_FILE=/dixie-detail.dump
QUOTE_PHOTO_HOST_DIR=${QUOTE_PHOTO_HOST_DIR:-/srv/dixie-quote-photos}
APP_UID=10001

# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "restore: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/errors.sh
. ops/lib/errors.sh
report_failures restore
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh
# shellcheck source=lib/settings.sh
. ops/lib/settings.sh

target=backup-server snapshot_id="" photo_id="" over=false
while (($#)); do
	case $1 in
		--from) target=$2; shift 2 ;;
		--snapshot) snapshot_id=$2; shift 2 ;;
		--photo-snapshot) photo_id=$2; shift 2 ;;
		--over-existing-data) over=true; shift ;;
		*) echo "usage: restore.sh [--from backup-server|b2|local] [--snapshot ID] [--photo-snapshot ID] [--over-existing-data]" >&2; exit 2 ;;
	esac
done
fail() { echo "restore: FAIL: $*" >&2; exit 1; }

db=$(setting POSTGRES_DB)
user=$(setting POSTGRES_USER)
: "${db:?set POSTGRES_DB in .env}" "${user:?set POSTGRES_USER in .env}"
systemctl is-active --quiet dixie-stack.service ||
	fail "dixie-stack.service isn't running; start it first (sudo systemctl start dixie-stack), so the database has its secrets"
psql_() { docker compose exec -T db psql -U "$user" -d "$db" -XAtq -v ON_ERROR_STOP=1 "$@"; }

# Has data: a customer or a user. A fresh stack's migrations create neither.
existing=$(psql_ -c "SELECT (SELECT count(*) FROM auth_user) + (SELECT count(*) FROM customers_customer)") ||
	fail "couldn't read the database; has the stack finished its first start (docker compose ps)?"
if ((existing > 0)) && ! $over; then
	fail "the database already has $existing customer(s) and user(s). Restoring would replace them. If that is what you want, run it again with --over-existing-data"
fi

restic_settings_from_env_file
restic_use "$target"
restic_load_any_secrets "$target"

if [[ -z $snapshot_id ]]; then
	snapshot=$(restic_newest_snapshot "$SNAPSHOT_FILE")
	[[ -n $snapshot ]] || fail "no database snapshots in $target"
	snapshot_id=$(jq -r .short_id <<<"$snapshot")
	echo "Database: snapshot $snapshot_id from $(TZ=America/New_York date -d "$(jq -r .time <<<"$snapshot")" '+%F %H:%M %Z')"
fi
if [[ -z $photo_id ]]; then
	photos=$(restic_newest_snapshot "$QUOTE_PHOTO_HOST_DIR")
	[[ -z $photos ]] || photo_id=$(jq -r .short_id <<<"$photos")
	[[ -n $photo_id ]] && echo "Photos: snapshot $photo_id from $(TZ=America/New_York date -d "$(jq -r .time <<<"$photos")" '+%F %H:%M %Z')" ||
		echo "Photos: no photo snapshot in $target; the photo folder is left as it is"
fi

work=$(mktemp -d /dev/shm/dixie-restore.XXXXXX)
# The photos are staged on disk next to their folder, not in memory.
staging=$(mktemp -d "$(dirname "$QUOTE_PHOTO_HOST_DIR")/dixie-photo-restore.XXXXXX")
trap 'rm -rf -- "$work" "$staging"' EXIT
# The local repository is read as rest-server's user (lib/restic.sh), which
# must be able to write the staging folder.
[[ $target != local ]] || chown "$REST_SERVER_UID:$REST_SERVER_UID" "$staging"
echo "Downloading the dump into memory"
restic_dump "$snapshot_id" "$SNAPSHOT_FILE" "$work/dixie-detail.dump"
docker compose exec -T db pg_restore --list <"$work/dixie-detail.dump" >/dev/null || fail "the downloaded dump isn't readable"

echo "Stopping everything but the database"
docker compose stop app public calendar-worker photo-worker caddy cloudflared

echo "Loading the dump into $db"
docker compose exec -T db pg_restore -U "$user" -d "$db" --clean --if-exists --no-owner --single-transaction --exit-on-error \
	<"$work/dixie-detail.dump" ||
	fail "pg_restore reported an error; nothing was changed (one transaction). The other containers are stopped: sudo systemctl restart dixie-stack starts them again"

if [[ -n $photo_id ]]; then
	echo "Writing the photos back to $QUOTE_PHOTO_HOST_DIR"
	install -d -m 0700 -o "$APP_UID" -g "$APP_UID" "$QUOTE_PHOTO_HOST_DIR"
	run_restic restore "$photo_id" --target "$staging"
	[[ -d $staging$QUOTE_PHOTO_HOST_DIR ]] || fail "snapshot $photo_id doesn't hold $QUOTE_PHOTO_HOST_DIR"
	rsync -a -- "$staging$QUOTE_PHOTO_HOST_DIR/" "$QUOTE_PHOTO_HOST_DIR/"
	chown -R "$APP_UID:$APP_UID" "$QUOTE_PHOTO_HOST_DIR"
	echo "Photos: $(find "$QUOTE_PHOTO_HOST_DIR" -type f -name '*.jpg' | wc -l) in $QUOTE_PHOTO_HOST_DIR"
fi

echo "Starting the stack"
systemctl restart dixie-stack.service
tables=$(psql_ -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
customers=$(psql_ -c "SELECT count(*) FROM customers_customer")
echo "restore: done: $tables tables, $customers customer(s), from $target snapshot $snapshot_id"
