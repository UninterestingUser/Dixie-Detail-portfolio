# shellcheck shell=bash
# The tunnel hold's marker file (decision 0128; see lib/stack.sh and
# ops/tunnel-hold.sh). Source it. Changed only by the tests.
TUNNEL_HOLD=${TUNNEL_HOLD:-/etc/dixie-detail/hold-tunnel}

# held_skip NAME: ends the script, successfully, when the tunnel is held:
# this host isn't production yet.
held_skip() {
	if [[ -e $TUNNEL_HOLD ]]; then
		echo "$1: the tunnel is held ($TUNNEL_HOLD): this host isn't production yet, so this run is skipped"
		exit 0
	fi
}
