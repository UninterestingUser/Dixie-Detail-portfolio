#!/usr/bin/env bash
# Restores the newest nightly snapshot from Google Drive into a throwaway
# PostgreSQL container and checks it. Run on the server as root:
#
#   sudo /srv/dixie-detail/ops/restore-test.sh
#
# The dump streams from restic straight into the container, whose data
# directory is in memory, so no plaintext copy lands on disk. The container
# has no network and is removed at the end, pass or fail.
#
# Checks: the newest snapshot is under 36 hours old, pg_restore finishes
# without an error, every table in the dump exists after the restore, and
# Django's migration table is there. Prints each table's row count.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
MAX_AGE_HOURS=36
SNAPSHOT_FILE=/dixie-detail.dump
container="dixie-restore-test-$$"

[[ $EUID -eq 0 ]] || { echo "restore-test: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh

restic_settings_from_env_file
restic_load_secrets "$bws_project_id"

psql_() { docker exec "$container" psql -U postgres -d restore_test -XAtq -v ON_ERROR_STOP=1 "$@"; }
fail() { echo "restore-test: FAIL: $*" >&2; exit 1; }

# Newest snapshot and its age.
snapshot=$(run_restic snapshots --host "$RESTIC_HOST" --tag nightly --json | jq -c 'max_by(.time) // empty')
[[ -n $snapshot ]] || fail "no nightly snapshots in $RESTIC_REPOSITORY"
snap_id=$(jq -r .short_id <<<"$snapshot")
snap_time=$(jq -r .time <<<"$snapshot")
age_hours=$((($(date +%s) - $(date -d "$snap_time" +%s)) / 3600))
echo "Newest snapshot: $snap_id from $(TZ=America/New_York date -d "$snap_time" '+%F %H:%M %Z') (${age_hours} h old)"
((age_hours < MAX_AGE_HOURS)) || fail "newest snapshot is ${age_hours} hours old"

# Throwaway PostgreSQL: same image as the stack, no network, data in memory.
image=$(docker compose config --format json | jq -r .services.db.image)
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run --detach --rm --name "$container" --network none \
	--tmpfs /var/lib/postgresql \
	-e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=restore_test \
	"$image" >/dev/null
# TCP only answers once initialisation is over and the real server is up.
for _ in $(seq 60); do
	docker exec "$container" pg_isready -q -h 127.0.0.1 && break
	sleep 1
done
docker exec "$container" pg_isready -q -h 127.0.0.1 || fail "throwaway PostgreSQL did not start"

echo "Restoring into $image"
expected=$(run_restic dump "$snap_id" "$SNAPSHOT_FILE" |
	docker exec -i "$container" pg_restore --list | awk '$4 == "TABLE"' | wc -l)
run_restic dump "$snap_id" "$SNAPSHOT_FILE" |
	docker exec -i "$container" pg_restore -U postgres -d restore_test --no-owner --no-privileges --exit-on-error ||
	fail "pg_restore reported an error"

restored=$(psql_ -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
echo "Tables: $expected in the dump, $restored restored"
((expected == restored)) || fail "table count does not match"
[[ $(psql_ -c "SELECT to_regclass('public.django_migrations') IS NOT NULL") == t ]] ||
	fail "django_migrations is missing"

echo "Row counts:"
psql_ -F $'\t' -c "
	SELECT schemaname || '.' || tablename,
	       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I', schemaname, tablename), false, true, '')))[1]
	FROM pg_tables
	WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
	ORDER BY 1" | sed 's/^/  /'

echo "restore-test: PASS"
