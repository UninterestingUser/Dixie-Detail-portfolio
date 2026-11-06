#!/usr/bin/env bash
# Morning sales tax rate check. Run by dixie-tax-rate-check.service
# (dixie-tax-rate-check.timer, every day at 5:15 AM).
#
# Runs `import_tax_rates --check` in a one-off app container: it reads the
# Tennessee Department of Revenue's rates, compares them with the stored
# ones, and stores any change to wait for the owner's approval on the control
# app's Sales tax screen. It never changes a rate in use, a boundary or a
# jurisdiction (docs/reference/sales-tax.md).
#
# HEALTHCHECKS_TAX_RATES_URL comes from Bitwarden at the start of the run, in
# one call, and lives only in this script's memory. Healthchecks gets a start
# ping, then:
#   - success when nothing waits for approval;
#   - failure, with the summary, while a rate change waits for approval or
#     the state lists an area the import has not loaded (exit status 2), so
#     the owner gets an email; the next morning's check after the owner acts
#     clears it;
#   - failure, with the log, when the check itself failed.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh

: "${RUNTIME_DIRECTORY:?run this from dixie-tax-rate-check.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"

# If this fails there is no ping URL either; Healthchecks reports the
# missing ping when the grace time runs out.
bws_load "$BWS_PROJECT_ID"
hc_url=$(bws_get_optional HEALTHCHECKS_TAX_RATES_URL)
bws_forget

log="$RUNTIME_DIRECTORY/tax-rate-check.log"
hc_ping "$hc_url" /start
set +e
docker compose run --rm --no-deps -T app python manage.py import_tax_rates --check 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
set -e

summary=$(grep -E '^Tax rate check:' "$log" | tail -n 1 || true)
if ((rc == 0)); then
	printf '%s\n' "${summary:-Tax rate check: nothing waiting}" >"$log.summary"
	hc_ping "$hc_url" "" "$log.summary"
elif ((rc == 2)); then
	{ printf 'Sales tax: a change is waiting for approval on the control app'"'"'s Sales tax screen.\n%s\n\n' "$summary"; tail -c 8000 "$log"; } >"$log.summary"
	hc_ping "$hc_url" /fail "$log.summary"
	echo "tax-rate-check: $summary"
	rc=0
else
	echo "tax-rate-check: the check failed with exit status $rc" >&2
	{ printf 'Tax rate check failed with exit status %s\n\n' "$rc"; tail -c 10000 "$log"; } >"$log.tail"
	hc_ping "$hc_url" /fail "$log.tail"
fi
exit "$rc"
