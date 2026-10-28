#!/usr/bin/env bash
# Monthly vehicle data refresh. Run by dixie-vehicle-refresh.service
# (dixie-vehicle-refresh.timer, the first Sunday of each month at 4:15 AM).
#
# Runs refresh_vehicle_data in a one-off app container with the download
# cache attached, as docs/operations/importing-vehicle-data.md runs the import
# by hand: import_vehicle_data --source all --refresh, then classify_vehicles
# --refresh, which holds in the review queue any class change to a model with
# an override, an approval or customers' jobs (decision 0081). Its output is
# the model years newly sent to the review queue and a one-line summary; the
# full reports appear only when it fails (decision 0083).
#
# HEALTHCHECKS_VEHICLE_REFRESH_URL comes from Bitwarden at the start of the
# run, in one call, and lives only in this script's memory. The container
# reads the database password from the stack's in-memory secret files, as
# every one-off app container does. Healthchecks gets a start ping, then a
# success or failure ping whose first line is the refresh's one-line summary.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-vehicle-refresh.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"

# The download cache on the host (created by ops/deploy.sh), mounted where the
# app's setting VEHICLE_DATA_CACHE_DIR looks by default.
CACHE_DIR=/srv/dixie-vehicle-data
CONTAINER_CACHE_DIR=/srv/vehicle-data

# If this fails there is no ping URL either; Healthchecks reports the
# missing ping when the grace time runs out.
# One Bitwarden call, retried if Bitwarden is rate-limiting.
bws_load "$BWS_PROJECT_ID"
hc_url=$(bws_get_optional HEALTHCHECKS_VEHICLE_REFRESH_URL)
bws_forget

refresh() {
	[[ -d $CACHE_DIR ]] || { echo "vehicle-refresh: $CACHE_DIR is missing; run ops/deploy.sh to create it" >&2; return 1; }
	docker compose run --rm --no-deps -T -v "$CACHE_DIR:$CONTAINER_CACHE_DIR" app \
		python manage.py refresh_vehicle_data
}

log="$RUNTIME_DIRECTORY/vehicle-refresh.log"
hc_ping "$hc_url" /start
set +e
(set -e; refresh) 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e

# refresh_vehicle_data prints the summary as its last line, pass or fail.
summary=$(grep -E '^Vehicle data refresh (succeeded|failed):' "$log" | tail -n 1 || true)
if ((rc == 0)); then
	printf '%s\n' "${summary:-Vehicle data refresh succeeded}" >"$log.summary"
	hc_ping "$hc_url" "" "$log.summary"
else
	[[ -n $summary ]] || summary="Vehicle data refresh failed with exit status $rc before it recorded a summary"
	echo "vehicle-refresh: $summary" >&2
	{ printf '%s\n\n' "$summary"; tail -c 10000 "$log"; } >"$log.tail"
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
