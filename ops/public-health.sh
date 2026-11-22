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
# shellcheck source=lib/healthchecks.sh
. ops/lib/healthchecks.sh

: "${PUBLIC_HEALTH_URL:?set PUBLIC_HEALTH_URL in .env}"
: "${CREDENTIALS_DIRECTORY:?run this from dixie-public-health.service}"

body=$(curl --fail --silent --show-error --max-time 20 \
	--retry 2 --retry-delay 10 --retry-all-errors "$PUBLIC_HEALTH_URL")
if ! printf '%s' "$body" | jq -e '.status == "ok"' >/dev/null 2>&1; then
	echo "public-health: $PUBLIC_HEALTH_URL answered: ${body:0:200}" >&2
	exit 1
fi

# The ping URL is its own systemd credential (decision 0125): this check runs
# every 10 minutes and never calls Bitwarden, whose rate limit it used to
# share with the backup and the stack's start (decision 0070).
hc_url=$(cat -- "$CREDENTIALS_DIRECTORY/healthchecks-public-url")
hc_ping "$hc_url" ""
