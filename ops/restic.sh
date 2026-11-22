#!/usr/bin/env bash
# Runs a restic command against one of the backup repositories (decision
# 0127), with its password and keys loaded for this one command: from
# Bitwarden on the production host, or from the backup host's own
# credentials there (decision 0126). Run as root:
#
#   sudo /srv/dixie-detail/ops/restic.sh snapshots                    # the backup server, over rest-server
#   sudo /srv/dixie-detail/ops/restic.sh --repo b2 snapshots          # Backblaze B2
#   sudo /srv/dixie-detail/ops/restic.sh --repo local check           # on the backup host, from its disk
#   sudo /srv/dixie-detail/ops/restic.sh --repo b2 init-labeled       # once, at setup
#
# init-labeled creates the repository with its one key labeled
# restic/restic, so no real host or user name is stored in it.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "restic.sh: run as root (sudo)" >&2; exit 1; }
cd "${DIXIE_DIR:-/srv/dixie-detail}"
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh

target=backup-server
if [[ ${1:-} == --repo ]]; then
	target=$2
	shift 2
fi
[[ $# -gt 0 ]] || { echo "usage: restic.sh [--repo backup-server|b2|local] COMMAND [ARGS...]" >&2; exit 2; }

restic_settings_from_env_file
restic_use "$target"
restic_load_any_secrets "$target"
if [[ $1 == init-labeled ]]; then
	restic_init_labeled
else
	run_restic "$@"
fi
