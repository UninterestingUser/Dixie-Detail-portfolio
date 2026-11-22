#!/usr/bin/env bash
# The requests-only switch (decision 0128). Run on the production host as
# root:
#
#   sudo /srv/dixie-detail/ops/site-mode.sh                         # shows the mode
#   sudo /srv/dixie-detail/ops/site-mode.sh requests "moving hosts"  # booking paused
#   sudo /srv/dixie-detail/ops/site-mode.sh normal
#
# In requests mode the public API's booking and quote endpoints answer 503,
# which the website treats as "server unavailable": customers get the
# request form, and Cloudflare's offline requests still reach the server.
# For maintenance, the move to a new host and outages. The mode is a row in
# the database, so it survives restarts until it is set back to normal.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "site-mode: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
args=()
case ${1:-} in
	"") ;;
	requests | normal) args=("$1" --reason "${2:-}") ;;
	*) echo "usage: site-mode.sh [requests [REASON] | normal]" >&2; exit 2 ;;
esac
docker compose exec -T app python manage.py site_mode "${args[@]}"
