#!/usr/bin/env bash
# Fetches the stack's secrets from Bitwarden, writes them as files to an
# in-memory directory, and starts the containers.
#
# Run by dixie-stack.service only. systemd supplies the Bitwarden token in
# $CREDENTIALS_DIRECTORY and the in-memory /run/dixie-stack directory, and
# loads the non-secret settings from .env.
#
# Any failure exits non-zero: Bitwarden unreachable or refusing (after the
# retries for a 429), a secret missing, or a container that doesn't come up
# running and healthy. The unit then tries again a minute later, for as long
# as it takes (Restart=on-failure, decision 0125), so the stack comes back
# by itself after a power or internet cut.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/stack.sh
. ops/lib/stack.sh

: "${CREDENTIALS_DIRECTORY:?run this from dixie-stack.service}"
: "${RUNTIME_DIRECTORY:?run this from dixie-stack.service}"
: "${BWS_PROJECT_ID:?set BWS_PROJECT_ID in .env}"

secrets_dir="$RUNTIME_DIRECTORY/secrets"
umask 077
# Start clean: Docker may have left empty placeholders here after a power cut.
rm -rf -- "$secrets_dir"

# One Bitwarden call for every secret, retried if Bitwarden is rate-limiting.
if ! bws_load "$BWS_PROJECT_ID"; then
	echo "stack-start: couldn't fetch the secrets from Bitwarden; trying again in a minute" >&2
	exit 1
fi
if ! stack_write_secrets "$secrets_dir"; then
	echo "stack-start: couldn't write the secret files; trying again in a minute" >&2
	exit 1
fi
bws_forget

# Recreate every container so each mounts the files just written. A container
# left from the last run would still hold the old ones.
if ! docker compose "${STACK_UP[@]}" --force-recreate; then
	echo "stack-start: the containers didn't all come up running and healthy; see docker compose ps. Trying again in a minute" >&2
	exit 1
fi
