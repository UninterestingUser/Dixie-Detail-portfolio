#!/usr/bin/env bash
# Fetches the stack's secrets from Bitwarden, writes them as files to an
# in-memory directory, and starts the containers.
#
# Run by dixie-stack.service only. systemd supplies the Bitwarden token in
# $CREDENTIALS_DIRECTORY and the in-memory /run/dixie-stack directory, and
# loads the non-secret settings from .env.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh

: "${CREDENTIALS_DIRECTORY:?run this from dixie-stack.service}"
: "${RUNTIME_DIRECTORY:?run this from dixie-stack.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"

# The users the containers run as. Each gets only its own secrets.
DB_UID=999        # postgres image
APP_UID=10001     # app/Dockerfile
TUNNEL_UID=65532  # cloudflared image (distroless nonroot)

secrets_dir="$RUNTIME_DIRECTORY/secrets"
umask 077
# Start clean: Docker may have left empty placeholders here after a power cut.
rm -rf -- "$secrets_dir"
mkdir -p "$secrets_dir"/{db,app,tunnel}

# One Bitwarden call for every secret, retried if Bitwarden is rate-limiting.
bws_load "$BWS_PROJECT_ID"

# put FILE BITWARDEN_KEY UID
put() {
	local file="$secrets_dir/$1"
	bws_get "$2" >"$file"
	chown "$3:0" "$file"
	chmod 0400 "$file"
}

put db/postgres_password      POSTGRES_PASSWORD       "$DB_UID"
put app/postgres_password     POSTGRES_PASSWORD       "$APP_UID"
put app/django_secret_key     DJANGO_SECRET_KEY       "$APP_UID"
put tunnel/cloudflared_token  CLOUDFLARE_TUNNEL_TOKEN "$TUNNEL_UID"
# put_optional FILE BITWARDEN_KEY UID: like put, but an empty file when the
# secret does not exist yet.
put_optional() {
	local file="$secrets_dir/$1"
	bws_get_optional "$2" >"$file"
	chown "$3:0" "$file"
	chmod 0400 "$file"
}

# Optional until the owner creates them. An empty Maps key means the app runs
# without Google (place lookups refused, drive times estimated); an empty
# service account key means the calendar sync waits (decision 0098).
put_optional app/google_maps_server_key       GOOGLE_MAPS_SERVER_KEY      "$APP_UID"
put_optional app/google_service_account_json  GOOGLE_SERVICE_ACCOUNT_JSON "$APP_UID"
bws_forget

# Recreate every container so each mounts the files just written. A container
# left from the last run would still hold the old ones.
exec docker compose up --detach --force-recreate --remove-orphans
