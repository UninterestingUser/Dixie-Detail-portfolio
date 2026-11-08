#!/usr/bin/env bash
# Nightly full check of the Google calendars. Run by dixie-calendar-check.service
# (dixie-calendar-check.timer, every night at 3:35 AM).
#
# Runs `sync_calendars` in a one-off app container: it pushes any queued
# Jobs calendar change, copies the Time Off calendar, then compares every
# appointment and closed date from today on with the Jobs calendar and
# repairs any difference (docs/reference/scheduling-and-calendars.md,
# decision 0098). The calendar worker does the same every few minutes; this
# run is the full check that reports to Healthchecks.
#
# HEALTHCHECKS_CALENDAR_CHECK_URL comes from Bitwarden at the start of the
# run, in one call, and lives only in this script's memory. Healthchecks gets
# a start ping, then success with the one-line summary, or failure with the
# end of the log when Google could not be asked or the check failed.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-calendar-check.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"

# If this fails there is no ping URL either; Healthchecks reports the
# missing ping when the grace time runs out.
bws_load "$BWS_PROJECT_ID"
hc_url=$(bws_get_optional HEALTHCHECKS_CALENDAR_CHECK_URL)
bws_forget

log="$RUNTIME_DIRECTORY/calendar-check.log"
hc_ping "$hc_url" /start
set +e
# The secret files are the ones the stack mounted from memory for the app
# (compose.yaml), so this run needs no Bitwarden call of its own for them.
docker compose run --rm --no-deps -T app python manage.py sync_calendars 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e

summary=$(grep -E '^Calendar check' "$log" | tail -n 1 || true)
if ((rc == 0)); then
	printf '%s\n' "${summary:-Calendar check: done}" >"$log.summary"
	hc_ping "$hc_url" "" "$log.summary"
else
	echo "calendar-check: the check failed with exit status $rc" >&2
	{ printf 'Calendar check failed with exit status %s\n%s\n\n' "$rc" "$summary"; tail -c 10000 "$log"; } >"$log.tail"
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
