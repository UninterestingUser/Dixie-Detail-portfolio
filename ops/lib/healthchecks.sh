# Healthchecks.io pings for ops scripts. Source it.

# hc_ping URL SUFFIX [BODY_FILE]
# Pings URL plus SUFFIX ("" for success, /start, /fail), optionally posting
# BODY_FILE. Does nothing if URL is empty. The URL goes to curl on stdin, so
# it never appears on a command line. A failed ping is reported but does not
# fail the caller.
hc_ping() {
	[[ -n $1 ]] || return 0
	local args=(--fail --silent --show-error --max-time 10 --retry 5 --output /dev/null)
	[[ -z ${3:-} ]] || args+=(--data-binary "@$3")
	printf 'url = "%s%s"\n' "$1" "$2" | curl "${args[@]}" --config - ||
		echo "Healthchecks ping failed" >&2
}
