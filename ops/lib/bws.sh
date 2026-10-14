# Shared Bitwarden helpers for ops scripts. Source it; do not run it.
#
# Secret values stay in shell variables and pipes. They are never written to
# disk, put on a command line, or exported to the environment of anything but
# bws itself.

# bws_project_secrets TOKEN PROJECT_ID
# Prints the project's secrets as bws JSON. Runs bws with a throwaway config
# in /dev/shm that turns off its on-disk state file. Needs BWS_SERVER_URL
# (from .env): a config profile without a server makes bws fail with
# "Profile has no `server_base` or `server_identity`".
bws_project_secrets() {
	local cfg rc=0
	: "${BWS_SERVER_URL:?set BWS_SERVER_URL in .env}"
	cfg=$(mktemp -d /dev/shm/dixie-bws.XXXXXX)
	printf '[profiles.default]\nstate_opt_out = "true"\n' >"$cfg/config"
	BWS_ACCESS_TOKEN="$1" BWS_CONFIG_FILE="$cfg/config" \
		bws secret list "$2" --server-url "$BWS_SERVER_URL" --output json --color no || rc=$?
	rm -rf -- "$cfg"
	return "$rc"
}

# bws_value JSON KEY
# Prints the value of the secret named KEY, with no trailing newline. Fails
# if no secret, or more than one, has that name.
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
