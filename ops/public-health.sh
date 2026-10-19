#!/usr/bin/env bash
# Fetches the public health page the way a customer's browser would reach the
# server: through Cloudflare and the tunnel. When it answers {"status":"ok"},
# pings the "public address" check on Healthchecks. Run every 10 minutes by
# dixie-public-health.timer.
#
# Only success is pinged. When the page is down, or the server or its
# internet connection is, the pings stop and Healthchecks raises the alert
# after the check's grace time.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh

: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"
: "${PUBLIC_HEALTH_URL:?set PUBLIC_HEALTH_URL in .env}"

body=$(curl --fail --silent --show-error --max-time 20 \
	--retry 2 --retry-delay 10 --retry-all-errors "$PUBLIC_HEALTH_URL")
if ! printf '%s' "$body" | jq -e '.status == "ok"' >/dev/null 2>&1; then
	echo "public-health: $PUBLIC_HEALTH_URL answered: ${body:0:200}" >&2
	exit 1
fi

# Fetched only after a good answer, and kept in memory for this run.
bws_load "$BWS_PROJECT_ID"
hc_url=$(bws_get HEALTHCHECKS_PUBLIC_URL)
bws_forget
hc_ping "$hc_url" ""
