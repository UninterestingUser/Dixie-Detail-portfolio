# Shared Bitwarden helpers for ops scripts. Source it; do not run it.
#
# Secret values stay in shell variables and pipes. They are never written to
# disk, put on a command line, or exported to the environment of anything but
# bws itself.

# How often and how long to wait when Bitwarden answers "429 Too Many
# Requests", which it does for about a minute when a machine account calls it
# too often. BWS_RETRY_SECONDS is changed only by the tests.
BWS_RETRIES=3
BWS_RETRY_SECONDS=${BWS_RETRY_SECONDS:-65}

# bws_project_secrets TOKEN PROJECT_ID
# Prints the project's secrets as bws JSON, from one `bws secret list` call.
# On a 429 it waits BWS_RETRY_SECONDS and tries again, up to BWS_RETRIES
# times, logging each retry to stderr. Runs bws with a throwaway config in
# /dev/shm that turns off its on-disk state file; bws's error messages go
# there too and never hold a secret. Needs BWS_SERVER_URL (from .env): a
# config profile without a server makes bws fail with "Profile has no
# `server_base` or `server_identity`".
bws_project_secrets() {
	local cfg out rc retry=0
	: "${BWS_SERVER_URL:?set BWS_SERVER_URL in .env}"
	cfg=$(mktemp -d /dev/shm/dixie-bws.XXXXXX)
	printf '[profiles.default]\nstate_opt_out = "true"\n' >"$cfg/config"
	while :; do
		rc=0
		out=$(BWS_ACCESS_TOKEN="$1" BWS_CONFIG_FILE="$cfg/config" \
			bws secret list "$2" --server-url "$BWS_SERVER_URL" --output json --color no 2>"$cfg/error") || rc=$?
		if ((rc == 0)); then
			printf '%s' "$out"
			break
		fi
		if ((retry < BWS_RETRIES)) && grep -qE '429|Too Many Requests' "$cfg/error"; then
			retry=$((retry + 1))
			echo "bws: Bitwarden is rate-limiting this machine account (429 Too Many Requests); retry $retry of $BWS_RETRIES in $BWS_RETRY_SECONDS seconds" >&2
			sleep "$BWS_RETRY_SECONDS"
			continue
		fi
		cat -- "$cfg/error" >&2
		break
	done
	unset out
	rm -rf -- "$cfg"
	return "$rc"
}

# bws_load PROJECT_ID
# Fetches every secret of the project once for this run, into the shell
# variable bws_secrets (never exported or written to disk), for bws_get and
# bws_get_optional. A second call reuses it, so a script calls Bitwarden at
# most once however many secrets it reads. Call it directly, not in $(...),
# or the result is lost. Every ops script fetches its secrets this way.
bws_load() {
	[[ -z ${bws_secrets:-} ]] || return 0
	local token
	token=$(bws_token) || return
	bws_secrets=$(bws_project_secrets "$token" "$1") || return
}

# bws_get KEY
# Prints the value of the secret named KEY from bws_load's result.
bws_get() {
	: "${bws_secrets:?bws_load was not called}"
	bws_value "$bws_secrets" "$1"
}

# bws_get_optional KEY
# Like bws_get, but prints nothing when no secret has that name.
bws_get_optional() {
	: "${bws_secrets:?bws_load was not called}"
	bws_optional_value "$bws_secrets" "$1"
}

# bws_forget
# Drops the fetched secrets from the shell once they have been read.
bws_forget() {
	unset bws_secrets
}

# bws_value JSON KEY
# Used by bws_get. Prints the value of the secret named KEY, with no trailing
# newline. Fails if no secret, or more than one, has that name.
bws_value() {
	printf '%s' "$1" | jq -je --arg key "$2" '
		[.[] | select(.key == $key)]
		| if length == 1 then .[0].value
		  else error("Bitwarden secret \($key): expected 1, found \(length)") end'
}

# bws_optional_value JSON KEY
# Like bws_value, but prints nothing when no secret has that name.
bws_optional_value() {
	printf '%s' "$1" | jq -je --arg key "$2" '
		[.[] | select(.key == $key)]
		| if length == 0 then ""
		  elif length == 1 then .[0].value
		  else error("Bitwarden secret \($key): expected 1, found \(length)") end'
}

# bws_token
# Prints the Bitwarden machine-account token. Under a unit with
# LoadCredentialEncrypted=bws-token:... it comes from the credentials
# directory; otherwise (a script run by hand as root) it is decrypted with
# systemd-creds straight into the pipe.
bws_token() {
	if [[ -n ${CREDENTIALS_DIRECTORY:-} && -r $CREDENTIALS_DIRECTORY/bws-token ]]; then
		cat -- "$CREDENTIALS_DIRECTORY/bws-token"
	else
		systemd-creds decrypt --name=bws-token /etc/credstore.encrypted/dixie-bws-token.cred -
	fi
}
