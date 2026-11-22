# shellcheck shell=bash
# Shared stack helpers for stack-start.sh and deploy.sh. Source after
# lib/bws.sh.

# The users the containers run as. Each gets only its own secrets.
DB_UID=999        # postgres image
APP_UID=10001     # app/Dockerfile; the app, public and calendar-worker services
TUNNEL_UID=65532  # cloudflared image (distroless nonroot)

# Where dixie-stack.service keeps the secret files while it runs (its
# RuntimeDirectory, in memory). STACK_RUN_DIR is changed only by the tests.
STACK_RUN_DIR=${STACK_RUN_DIR:-/run/dixie-stack}

# How `docker compose up` is run: in the background, removing containers of
# services that are gone, and waiting until every service is running and
# healthy, so a container that fails to start fails the command.
# shellcheck disable=SC2034 # used by the scripts that source this file
STACK_UP=(up --detach --remove-orphans --wait --wait-timeout 600)

# The tunnel hold (decision 0128). While this file exists, this host isn't
# production yet: the stack starts without its tunnel connector and without
# the calendar worker (both scaled to 0), and the backups and the calendar
# check skip their runs. So a new production host can be restored and
# checked while the old host still runs production: two connectors with the
# same token would split the public traffic between the hosts, two calendar
# workers would both write to Google, and the new host's backups would add
# snapshots of a copy that is about to be replaced. ops/tunnel-hold.sh sets
# and clears it. lib/hold.sh holds the path. Changed only by the tests.
# shellcheck source=hold.sh
. "$(dirname "${BASH_SOURCE[0]}")/hold.sh"
if [[ -e $TUNNEL_HOLD ]]; then
	STACK_UP+=(--scale cloudflared=0 --scale calendar-worker=0)
fi

# stack_hold_note: says so when the tunnel is held.
stack_hold_note() {
	[[ ! -e $TUNNEL_HOLD ]] || echo "stack: the tunnel is held ($TUNNEL_HOLD): starting without cloudflared and the calendar worker; ops/tunnel-hold.sh off starts them" >&2
}

# The health check's Healthchecks ping URL, as its own systemd credential
# (decision 0125), so the 10-minute check never calls Bitwarden.
HEALTH_CRED_NAME=healthchecks-public-url
HEALTH_CRED=${HEALTH_CRED:-/etc/credstore.encrypted/dixie-healthchecks-public-url.cred}

# stack_write_secrets DIR
# Writes every secret file the containers mount into DIR (a fresh folder on
# tmpfs), from bws_load's result: db/, app/ and tunnel/, each file owned by
# the user its container runs as, mode 0400. Fails on the first secret it
# can't read.
stack_write_secrets() {
	local dir=$1
	(
		umask 077
		mkdir -p "$dir"/{db,app,tunnel}
	)
	_stack_put() { # FILE BITWARDEN_KEY UID GETTER
		local file="$dir/$1"
		"$4" "$2" >"$file" || return
		chown "$3:0" "$file" && chmod 0400 "$file"
	}
	_stack_put db/postgres_password      POSTGRES_PASSWORD       "$DB_UID" bws_get || return
	_stack_put app/postgres_password     POSTGRES_PASSWORD       "$APP_UID" bws_get || return
	_stack_put app/django_secret_key     DJANGO_SECRET_KEY       "$APP_UID" bws_get || return
	_stack_put tunnel/cloudflared_token  CLOUDFLARE_TUNNEL_TOKEN "$TUNNEL_UID" bws_get || return
	# Optional until the owner creates them: an empty file when the secret
	# does not exist yet. An empty Maps key means the app runs without Google
	# (place lookups refused, drive times estimated); an empty service account
	# key means the calendar sync waits (decision 0098); an empty Turnstile key
	# means every booking and quote request is refused; an empty signing key
	# means offline requests are refused (decision 0100); an empty deploy hook
	# means publishing a pricebook asks for no rebuild.
	_stack_put app/google_maps_server_key        GOOGLE_MAPS_SERVER_KEY       "$APP_UID" bws_get_optional || return
	_stack_put app/google_service_account_json   GOOGLE_SERVICE_ACCOUNT_JSON  "$APP_UID" bws_get_optional || return
	_stack_put app/turnstile_secret_key          TURNSTILE_SECRET_KEY         "$APP_UID" bws_get_optional || return
	_stack_put app/offline_requests_signing_key  OFFLINE_REQUESTS_SIGNING_KEY "$APP_UID" bws_get_optional || return
	_stack_put app/cloudflare_pages_deploy_hook  CLOUDFLARE_PAGES_DEPLOY_HOOK "$APP_UID" bws_get_optional || return
}

# stack_write_health_credential
# Encrypts the Bitwarden secret HEALTHCHECKS_PUBLIC_URL, from bws_load's
# result, into HEALTH_CRED with systemd-creds, bound to this host and its
# TPM like the Bitwarden token. The value goes through a pipe only.
stack_write_health_credential() {
	local url
	url=$(bws_get HEALTHCHECKS_PUBLIC_URL) || return
	printf '%s' "$url" | systemd-creds encrypt --with-key=host+tpm2 --name="$HEALTH_CRED_NAME" - "$HEALTH_CRED"
}
