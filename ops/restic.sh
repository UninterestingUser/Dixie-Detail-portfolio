#!/usr/bin/env bash
# Runs a restic command against the Drive repository, with the passwords
# fetched from Bitwarden for this one command. Run on the server as root:
#
#   sudo /srv/dixie-detail/ops/restic.sh init          # once, at setup
#   sudo /srv/dixie-detail/ops/restic.sh snapshots
#   sudo /srv/dixie-detail/ops/restic.sh check
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "restic.sh: run as root (sudo)" >&2; exit 1; }
cd "${DIXIE_DIR:-/srv/dixie-detail}"
# shellcheck source=lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=lib/restic.sh
. ops/lib/restic.sh

restic_settings_from_env_file
restic_load_secrets "$bws_project_id"
run_restic "$@"
