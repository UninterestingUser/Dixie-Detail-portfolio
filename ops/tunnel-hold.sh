#!/usr/bin/env bash
# The tunnel hold (decision 0128): runs the stack without its tunnel
# connector, for the move to a new production host. Two connectors with the
# same tunnel token split the public traffic between two hosts, so only one
# may run at any moment (docs/operations/moving-production.md). Run as root:
#
#   sudo /srv/dixie-detail/ops/tunnel-hold.sh on       # before the new host's first start
#   sudo /srv/dixie-detail/ops/tunnel-hold.sh status
#   sudo /srv/dixie-detail/ops/tunnel-hold.sh off      # once the old host's connector is stopped
#
# on stops this host's connector and calendar worker if they run, keeps them
# stopped through restarts and deploys, and makes the backups and the
# calendar check skip their runs (lib/stack.sh). off asks you to confirm the
# other host's connector is stopped, then starts this one's.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "tunnel-hold: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/stack.sh
. ops/lib/stack.sh

case ${1:-} in
	on)
		mkdir -p "$(dirname "$TUNNEL_HOLD")"
		touch "$TUNNEL_HOLD"
		if systemctl is-active --quiet dixie-stack.service; then
			docker compose stop cloudflared calendar-worker
		fi
		echo "tunnel-hold: on. This host's tunnel connector and calendar worker are stopped, and its backups skip, until: ops/tunnel-hold.sh off"
		;;
	off)
		echo "Only one tunnel connector may run. Check the other host's is stopped:"
		echo "  on the other host, docker compose ps cloudflared shows nothing running, and"
		echo "  Cloudflare's dashboard (Networking, Tunnels, dixie-detail) shows no connector."
		read -rp "Type yes when it is: " answer <"${DIXIE_TTY:-/dev/tty}"
		[[ $answer == yes ]] || { echo "tunnel-hold: still on; nothing changed" >&2; exit 1; }
		rm -f -- "$TUNNEL_HOLD"
		if systemctl is-active --quiet dixie-stack.service; then
			# Sourced again, now without the hold.
			. ops/lib/stack.sh
			docker compose "${STACK_UP[@]}"
		fi
		echo "tunnel-hold: off. This host's tunnel connector and calendar worker run, and its backups are back on"
		;;
	status)
		if [[ -e $TUNNEL_HOLD ]]; then echo "tunnel-hold: on"; else echo "tunnel-hold: off"; fi
		;;
	*) echo "usage: tunnel-hold.sh on|off|status" >&2; exit 2 ;;
esac
