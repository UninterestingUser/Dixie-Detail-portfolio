#!/usr/bin/env bash
# Creates or refreshes the public health check's ping URL credential
# (decision 0125): the Bitwarden secret HEALTHCHECKS_PUBLIC_URL, encrypted
# with systemd-creds to /etc/credstore.encrypted/
# dixie-healthchecks-public-url.cred, bound to this host and its TPM like the
# Bitwarden token. dixie-public-health.service loads it, so the 10-minute
# check never calls Bitwarden. Run on the server as root:
#
#   sudo /srv/dixie-detail/ops/health-credential.sh
#
# deploy.sh runs it when the credential is missing. Run it by hand after
# changing the ping URL in Bitwarden.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
[[ $EUID -eq 0 ]] || { echo "health-credential: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/settings.sh
. ops/lib/settings.sh
# shellcheck source=lib/stack.sh
. ops/lib/stack.sh

project_id=$(setting BWS_PROJECT_ID)
: "${project_id:?set BWS_PROJECT_ID in .env}"
server_url=$(setting BWS_SERVER_URL)
[[ -z $server_url ]] || export BWS_SERVER_URL="$server_url"

bws_load "$project_id"
stack_write_health_credential
bws_forget
echo "health-credential: wrote $HEALTH_CRED"
