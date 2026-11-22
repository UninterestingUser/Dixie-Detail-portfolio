# shellcheck shell=bash
# Shared restic helpers for ops scripts. Source after lib/bws.sh.
#
# Three repositories, all with the one RESTIC_PASSWORD (decision 0127):
#   backup-server  the backup host's rest-server, over TLS with its
#                  certificate pinned, append-only: the production host can
#                  add snapshots but never delete them;
#   b2             Backblaze B2, through restic's S3-compatible backend;
#   local          the backup server's repository read straight from the
#                  backup host's disk, as rest-server's own user, for the
#                  weekly prune and restore test there.
# restic_use NAME picks one. Every password and key is kept in a shell
# variable and handed only to the restic process, in its environment.

RESTIC_HOST=dixie-detail
# rest-server's user name, and its private repository's folder.
REST_USER=dixie-detail
# The user rest-server runs as on the backup host; files in its data folder
# belong to it, so the local restic runs as it too.
REST_SERVER_UID=10010
# That user's restic cache for the local repository. Changed only by tests.
RESTIC_LOCAL_CACHE=${RESTIC_LOCAL_CACHE:-/var/cache/dixie-restic-local}
# The host and user labels on a repository's key, the only plain text in a
# repository (decision 0127). restic init has no option for them, so
# restic_init_labeled swaps the first key for one with these labels.
RESTIC_KEY_LABEL=restic
# The backup host's own credentials (decision 0126). Changed only by tests.
HOST_CRED_DIR=${HOST_CRED_DIR:-/etc/credstore.encrypted}
BWS_TOKEN_CRED=${BWS_TOKEN_CRED:-/etc/credstore.encrypted/dixie-bws-token.cred}

# restic_settings_from_env_file
# For scripts run by hand: reads the non-secret settings the repositories
# need from .env in the current directory and sets bws_project_id (empty on
# the backup host, which has no Bitwarden). Units get these through
# EnvironmentFile= instead. Call it directly, not in $(...), or the values
# are lost.
restic_settings_from_env_file() {
	local key value
	# shellcheck source=settings.sh
	. ops/lib/settings.sh
	for key in BACKUP_HOST_ADDRESS BACKUP_REST_PORT BACKUP_REST_CACERT BACKUP_REST_DATA_DIR B2_REPOSITORY BWS_SERVER_URL BWS_PROJECT_ID; do
		value=$(setting "$key")
		[[ -z $value ]] || export "$key=$value"
	done
	bws_project_id=${BWS_PROJECT_ID:-}
}

# restic_use NAME
# Points run_restic at a repository: backup-server, b2 or local. Fails with
# a message when a setting it needs is missing.
restic_use() {
	restic_target=$1
	restic_args=()
	restic_as=()
	restic_cache_dir=""
	case $1 in
		backup-server)
			: "${BACKUP_HOST_ADDRESS:?set BACKUP_HOST_ADDRESS in .env}"
			: "${BACKUP_REST_CACERT:?set BACKUP_REST_CACERT in .env}"
			restic_repository="rest:https://$BACKUP_HOST_ADDRESS:${BACKUP_REST_PORT:-8443}/$REST_USER/"
			restic_args=(--cacert "$BACKUP_REST_CACERT")
			;;
		b2)
			: "${B2_REPOSITORY:?set B2_REPOSITORY in .env}"
			restic_repository=$B2_REPOSITORY
			;;
		local)
			: "${BACKUP_REST_DATA_DIR:?set BACKUP_REST_DATA_DIR in .env}"
			restic_repository="$BACKUP_REST_DATA_DIR/$REST_USER"
			restic_as=(setpriv --reuid="$REST_SERVER_UID" --regid="$REST_SERVER_UID" --clear-groups)
			restic_cache_dir=$RESTIC_LOCAL_CACHE
			;;
		*)
			echo "restic: unknown repository '$1' (backup-server, b2 or local)" >&2
			return 1
			;;
	esac
}

# restic_load_secrets PROJECT_ID TARGET...
# Sets restic_password, and what each TARGET needs (rest_password for
# backup-server; b2_key_id and b2_application_key for b2), from Bitwarden,
# with one call through bws_load.
restic_load_secrets() {
	local project=$1 target
	shift
	bws_load "$project" || return
	restic_password=$(bws_get RESTIC_PASSWORD) || return
	for target; do
		case $target in
			backup-server) rest_password=$(bws_get BACKUP_REST_PASSWORD) || return ;;
			b2)
				b2_key_id=$(bws_get B2_KEY_ID) || return
				b2_application_key=$(bws_get B2_APPLICATION_KEY) || return
				;;
		esac
	done
	bws_forget
}

# host_credential NAME
# Prints one of the backup host's own credentials (decision 0126): from the
# unit's credentials directory, or decrypted with systemd-creds for a
# script run by hand as root.
host_credential() {
	if [[ -n ${CREDENTIALS_DIRECTORY:-} && -r $CREDENTIALS_DIRECTORY/$1 ]]; then
		cat -- "$CREDENTIALS_DIRECTORY/$1"
	else
		systemd-creds decrypt --name="$1" "$HOST_CRED_DIR/dixie-$1.cred" -
	fi
}

# restic_load_any_secrets TARGET...
# On a host with the Bitwarden token, restic_load_secrets. On the backup
# host, which has none, RESTIC_PASSWORD comes from its own credential, and
# the B2 keys, which it never stores, are asked for (pasted, never shown).
restic_load_any_secrets() {
	local target
	if [[ -f $BWS_TOKEN_CRED || -r ${CREDENTIALS_DIRECTORY:-/nonexistent}/bws-token ]]; then
		: "${bws_project_id:?set BWS_PROJECT_ID in .env}"
		restic_load_secrets "$bws_project_id" "$@"
		return
	fi
	restic_password=$(host_credential restic-password) || return
	for target; do
		case $target in
			backup-server) echo "restic: the backup host reads its repository as local, not over rest-server" >&2; return 1 ;;
			b2)
				read -rsp "B2_KEY_ID (from Bitwarden; not shown): " b2_key_id <"${DIXIE_TTY:-/dev/tty}" && echo >&2
				read -rsp "B2_APPLICATION_KEY (from Bitwarden; not shown): " b2_application_key <"${DIXIE_TTY:-/dev/tty}" && echo >&2
				;;
		esac
	done
}

# gnu_timeout
# Prints the name of a GNU coreutils timeout, or fails with a message.
# run_restic needs GNU's: on Ubuntu 26.04 `timeout` is uutils' 0.10.0, which,
# given --signal=INT together with --kill-after, sends SIGKILL at once instead
# of SIGINT, so a restic cut off at its time limit leaves its lock behind.
# 26.04 also installs GNU's as /usr/bin/gnutimeout (package gnu-coreutils);
# Fedora has GNU's as `timeout`. tools/test-timeout.sh checks the one this
# picks.
gnu_timeout() {
	local candidate
	for candidate in gnutimeout timeout; do
		if command -v "$candidate" >/dev/null && [[ $("$candidate" --version 2>/dev/null) == *"GNU coreutils"* ]]; then
			echo "$candidate"
			return 0
		fi
	done
	echo "restic: no GNU coreutils timeout found: /usr/bin/gnutimeout is missing. Install it with: sudo apt install gnu-coreutils (26.04's own timeout, uutils', kills restic without letting it remove its lock)" >&2
	return 1
}

# run_restic ARGS...
# Runs restic against the repository restic_use picked, with its password
# and keys in restic's environment only. Stops with a clear error, before
# starting restic, when no GNU timeout is installed. When the caller sets
# restic_time_limit (a duration for timeout(1), such as 8m), restic gets
# that long: then SIGINT, on which restic removes its lock and stops, and
# SIGKILL a minute later if it is still running (status 124 or 137). The
# last 1500 bytes of restic's error output are left in restic_last_error
# for the caller. restic's stdout must never go into a pipe: a reader that
# stops early kills restic with SIGPIPE mid-command, and a killed restic
# leaves its lock in the repository (the 2026-11-03 incident). Capture the
# output with $(...), which reads it all, or send it to a file with
# restic_dump. tools/test-restic.sh checks that no ops script pipes it.
# When the repository is locked, restic's own error is followed by
# restic_lock_hint.
run_restic() {
	local err rc=0 limit=() timeout_cmd
	: "${restic_repository:?restic_use was not called}"
	timeout_cmd=$(gnu_timeout) || return
	[[ -z ${restic_time_limit:-} ]] || limit=("$timeout_cmd" --signal=INT --kill-after=1m "$restic_time_limit")
	err=$(mktemp /dev/shm/dixie-restic.XXXXXX) || return
	# restic's errors go to the terminal or log as they come, and to $err to
	# be checked. The braces make this shell, not restic's, start tee, so
	# $! is tee's PID and the wait lets it finish before $err is read. The
	# secrets go in as variable assignments, which reach restic's
	# environment and never a command line. RESTIC_FROM_PASSWORD is the
	# same password: every repository uses it, so `restic copy` works.
	{
		RESTIC_REPOSITORY="$restic_repository" RESTIC_PASSWORD="$restic_password" RESTIC_FROM_PASSWORD="$restic_password" \
			RESTIC_REST_USERNAME="$REST_USER" RESTIC_REST_PASSWORD="${rest_password:-}" \
			AWS_ACCESS_KEY_ID="${b2_key_id:-}" AWS_SECRET_ACCESS_KEY="${b2_application_key:-}" \
			RESTIC_CACHE_DIR="${restic_cache_dir:-${RESTIC_CACHE_DIR:-}}" \
			"${limit[@]}" "${restic_as[@]}" restic "${restic_args[@]}" "$@"
	} 2> >(tee -- "$err" >&2) || rc=$?
	wait "$!" 2>/dev/null || true
	# shellcheck disable=SC2034 # read by the callers
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
	cat <<-HINT
		restic: the backup repository is locked. If no other restic command is
		running (\`pgrep -a restic\` prints nothing on either host), the lock is
		stale: a restic that was cut off left it behind. Remove it with
		  sudo /srv/dixie-detail/ops/restic.sh --repo ${restic_target:-backup-server} unlock
		then run this again. \`unlock\` removes only stale locks. See
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

# restic_init_labeled
# Creates the repository restic_use picked, then replaces its first key with
# one labeled host and user "restic", so no real host or user name is
# stored in it (decision 0127). A repository that already exists is left
# alone. Needs the right to delete keys: run it against b2 or local, never
# through the append-only rest-server.
restic_init_labeled() {
	local keys first labeled
	if run_restic cat config >/dev/null 2>&1; then
		echo "restic: $restic_target already has a repository; left as it is"
		return 0
	fi
	run_restic init || return
	keys=$(run_restic key list --json) || return
	first=$(jq -r '.[0].id' <<<"$keys")
	# The new key's password (the same one) on restic's stdin, which works
	# for a restic running as another user too, unlike a /dev/fd path.
	printf '%s' "$restic_password" | run_restic key add --host "$RESTIC_KEY_LABEL" --user "$RESTIC_KEY_LABEL" || return
	keys=$(run_restic key list --json) || return
	labeled=$(jq -r --arg first "$first" '[.[] | select(.id != $first)][0].id' <<<"$keys")
	run_restic key remove --key-hint "$labeled" "$first" || return
	keys=$(run_restic key list --json) || return
	jq -e --arg label "$RESTIC_KEY_LABEL" 'length == 1 and .[0].userName == $label and .[0].hostName == $label' <<<"$keys" >/dev/null ||
		{ echo "restic: the repository's key isn't labeled $RESTIC_KEY_LABEL/$RESTIC_KEY_LABEL" >&2; return 1; }
	echo "restic: created $restic_target, its one key labeled $RESTIC_KEY_LABEL/$RESTIC_KEY_LABEL"
}

# restic_newest_snapshot PATH
# Prints the newest snapshot holding PATH, as one line of JSON, or nothing.
restic_newest_snapshot() {
	local listing
	listing=$(run_restic snapshots --host "$RESTIC_HOST" --path "$1" --json) || return
	jq -c 'max_by(.time) // empty' <<<"$listing"
}
