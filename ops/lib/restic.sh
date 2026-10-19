# Shared restic helpers for ops scripts. Source after lib/bws.sh.
#
# RESTIC_PASSWORD and RCLONE_CONFIG_PASS are kept in shell variables and
# handed only to the restic process (and the rclone process restic starts).

RESTIC_HOST=dixie-detail

# restic_settings_from_env_file
# For scripts run by hand: exports the non-secret restic settings from .env
# in the current directory and sets bws_project_id. (Units get these through
# EnvironmentFile= instead.) Call it directly, not in $(...), or the exports
# are lost.
restic_settings_from_env_file() {
	local value
	# shellcheck source=settings.sh
	. ops/lib/settings.sh
	RESTIC_REPOSITORY=$(setting RESTIC_REPOSITORY)
	: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY in .env}"
	export RESTIC_REPOSITORY
	value=$(setting RCLONE_CONFIG)
	[[ -z $value ]] || export RCLONE_CONFIG="$value"
	value=$(setting BWS_SERVER_URL)
	[[ -z $value ]] || export BWS_SERVER_URL="$value"
	bws_project_id=$(setting BWS_PROJECT_ID)
	: "${bws_project_id:?set BWS_PROJECT_ID in .env}"
}

# restic_load_secrets PROJECT_ID
# Sets restic_password and rclone_config_pass from Bitwarden, with one call
# through bws_load.
restic_load_secrets() {
	bws_load "$1" || return
	restic_password=$(bws_get RESTIC_PASSWORD)
	rclone_config_pass=$(bws_get RCLONE_CONFIG_PASS)
	bws_forget
}

run_restic() {
	RESTIC_PASSWORD="$restic_password" RCLONE_CONFIG_PASS="$rclone_config_pass" \
		restic "$@"
}
