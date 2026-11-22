# Shared restic helpers for ops scripts. Source after lib/bws.sh.
#
# RESTIC_PASSWORD and RCLONE_CONFIG_PASS are kept in shell variables and
# handed only to the restic process (and the rclone process restic starts).

RESTIC_HOST=dixie-detail

# Options every restic command gets. restic waits 1 minute by default for
# rclone to open the repository on Google Drive; on 2026-10-31 and
# 2026-11-06 a slow Drive took longer and the backup failed before it
# uploaded anything (decision 0089).
RESTIC_OPTIONS=(-o rclone.timeout=5m)
# Drive calls a second for the rclone that restic starts, through rclone's
# RCLONE_TPSLIMIT, which rclone reads from the environment restic hands it.
# Not through -o rclone.args, which would replace restic's whole default
# rclone command line.
RESTIC_RCLONE_TPSLIMIT=5

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

# gnu_timeout
# Prints the name of a GNU coreutils timeout, or fails with a message.
# run_restic needs GNU's: on Ubuntu 26.04 `timeout` is uutils' 0.10.0, which,
# given --signal=INT together with --kill-after, sends SIGKILL at once instead
# of SIGINT, so a restic cut off at its time limit leaves its lock behind.
# 26.04 also installs GNU's as `gnutimeout` (package gnu-coreutils, priority
# required); 24.04 and Fedora have GNU's as `timeout`. tools/test-timeout.sh
# checks the one this picks.
gnu_timeout() {
	local candidate
	for candidate in gnutimeout timeout; do
		if command -v "$candidate" >/dev/null && [[ $("$candidate" --version 2>/dev/null) == *"GNU coreutils"* ]]; then
			echo "$candidate"
			return 0
		fi
	done
	echo "restic: no GNU coreutils timeout found (the uutils one kills restic without letting it remove its lock); install gnu-coreutils" >&2
	return 1
}

# run_restic ARGS...
# Runs restic with the passwords, RESTIC_OPTIONS and RESTIC_RCLONE_TPSLIMIT.
# When the caller sets restic_time_limit (a duration for timeout(1), such as
# 8m), restic gets that long: then SIGINT, on which restic removes its lock
# and stops, and SIGKILL a minute later if it is still running (status 124
# or 137). The last 1500 bytes of restic's error output are left in
# restic_last_error for the caller. restic's stdout must never go into a pipe:
# a reader that stops early kills restic with SIGPIPE mid-command, and a
# killed restic leaves its lock in the repository, which makes the next
# `forget --prune` fail until someone runs `ops/restic.sh unlock` (the
# 2026-11-03 incident). Capture the output with $(...), which reads it all,
# or send it to a file with restic_dump. tools/test-restic.sh checks that no
# ops script pipes it. When the repository is locked, restic's own error is
# followed by restic_lock_hint.
run_restic() {
	local err rc=0 limit=() timeout_cmd
	if [[ -n ${restic_time_limit:-} ]]; then
		timeout_cmd=$(gnu_timeout) || return
		limit=("$timeout_cmd" --signal=INT --kill-after=1m "$restic_time_limit")
	fi
	err=$(mktemp /dev/shm/dixie-restic.XXXXXX) || return
	# restic's errors go to the terminal or log as they come, and to $err to
	# be checked. The braces make this shell, not restic's, start tee, so
	# $! is tee's PID and the wait lets it finish before $err is read.
	{
		RESTIC_PASSWORD="$restic_password" RCLONE_CONFIG_PASS="$rclone_config_pass" \
			RCLONE_TPSLIMIT="$RESTIC_RCLONE_TPSLIMIT" "${limit[@]}" restic "${RESTIC_OPTIONS[@]}" "$@"
	} 2> >(tee -- "$err" >&2) || rc=$?
	wait "$!" 2>/dev/null || true
	restic_last_error=$(tail -c 1500 -- "$err")
	# restic 0.17 and later exit with 11 when they cannot lock the repository.
	if ((rc != 0)) && { ((rc == 11)) || grep -q 'repository is already locked' -- "$err"; }; then
		restic_lock_hint >&2
	fi
	rm -f -- "$err"
	return "$rc"
}

# restic_lock_hint
# Says what to do about a locked repository, naming the unlock command.
restic_lock_hint() {
	cat <<-'HINT'
		restic: the backup repository is locked. If no other restic command is
		running on the server (`pgrep -a restic` prints nothing), the lock is
		stale: a restic that was cut off left it behind. Remove it with
		  sudo /srv/dixie-detail/ops/restic.sh unlock
		then run this again. `unlock` removes only stale locks. See
		"The backup repository is locked" in docs/operations/troubleshooting.md.
	HINT
}

# restic_dump SNAPSHOT PATH OUT
# Writes the file PATH from SNAPSHOT to the file OUT. restic writes to the
# file, not to a pipe, so nothing that reads the dump afterwards can cut it
# off however little of it that reader wants.
restic_dump() {
	run_restic dump "$1" "$2" >"$3"
}
