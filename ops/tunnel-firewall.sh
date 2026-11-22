#!/usr/bin/env bash
# The tunnel network's firewall on the host (decision 0125). cloudflared is
# the only container on the "tunnel" Docker network besides Caddy. If it, or
# anything else that got onto that network, were taken over, these rules
# keep it from reaching anything but Caddy's public door and the internet:
#
#   - to Caddy's public door (172.31.250.20, TCP 8080): allowed;
#   - to private ranges (10/8, 172.16/12, 192.168/16, 100.64/10 for the
#     tailnet, 169.254/16), which covers the LAN, the tailnet, the other
#     Docker networks and Caddy's other ports: dropped;
#   - to the host itself, on any of its addresses: dropped (INPUT);
#   - to public internet addresses (Cloudflare's edge, public DNS): allowed.
# Replies to allowed connections are always allowed.
#
# Two chains of its own, DIXIE-TUNNEL (from DOCKER-USER, for forwarded
# traffic) and DIXIE-TUNNEL-HOST (from INPUT), replaced together in one
# atomic iptables-restore, so applying again never leaves a gap. Docker
# leaves DOCKER-USER to the owner. Run by dixie-tunnel-firewall.service,
# after Docker starts:
#
#   tunnel-firewall.sh apply     add or replace the rules
#   tunnel-firewall.sh remove    take them out
#   tunnel-firewall.sh print     print the rules, change nothing
#
# Check them with ops/check-tunnel-isolation.sh. IPv4 only: the tunnel
# network has no IPv6. IPTABLES changes the command, for the tests.
set -euo pipefail

TUNNEL_SUBNET=172.31.250.0/24
CADDY_TUNNEL_IP=172.31.250.20
CADDY_PUBLIC_PORT=8080
PRIVATE_RANGES=(10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16)
IPTABLES=${IPTABLES:-iptables}
read -r -a iptables <<<"$IPTABLES"
restore=("${iptables[@]}")
restore[0]="${iptables[0]}-restore"

rules() {
	echo "*filter"
	echo ":DIXIE-TUNNEL - [0:0]"
	echo ":DIXIE-TUNNEL-HOST - [0:0]"
	echo "-A DIXIE-TUNNEL -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN"
	echo "-A DIXIE-TUNNEL -d $CADDY_TUNNEL_IP/32 -p tcp -m tcp --dport $CADDY_PUBLIC_PORT -j RETURN"
	local range
	for range in "${PRIVATE_RANGES[@]}"; do
		echo "-A DIXIE-TUNNEL -d $range -j DROP"
	done
	echo "-A DIXIE-TUNNEL -j RETURN"
	echo "-A DIXIE-TUNNEL-HOST -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
	echo "-A DIXIE-TUNNEL-HOST -j DROP"
	echo "COMMIT"
}

# jump CHAIN TARGET: make sure CHAIN sends the tunnel's traffic to TARGET,
# once, at the top.
jump() {
	"${iptables[@]}" -C "$1" -s "$TUNNEL_SUBNET" -j "$2" 2>/dev/null ||
		"${iptables[@]}" -I "$1" 1 -s "$TUNNEL_SUBNET" -j "$2"
}

unjump() {
	while "${iptables[@]}" -C "$1" -s "$TUNNEL_SUBNET" -j "$2" 2>/dev/null; do
		"${iptables[@]}" -D "$1" -s "$TUNNEL_SUBNET" -j "$2"
	done
}

case ${1:-} in
apply)
	"${iptables[@]}" -n -L DOCKER-USER >/dev/null 2>&1 || {
		echo "tunnel-firewall: Docker's DOCKER-USER chain is missing; is Docker running, with its iptables firewall?" >&2
		exit 1
	}
	rules | "${restore[@]}" --noflush
	jump DOCKER-USER DIXIE-TUNNEL
	jump INPUT DIXIE-TUNNEL-HOST
	echo "tunnel-firewall: rules applied for $TUNNEL_SUBNET"
	;;
remove)
	unjump DOCKER-USER DIXIE-TUNNEL
	unjump INPUT DIXIE-TUNNEL-HOST
	for chain in DIXIE-TUNNEL DIXIE-TUNNEL-HOST; do
		"${iptables[@]}" -F "$chain" 2>/dev/null || true
		"${iptables[@]}" -X "$chain" 2>/dev/null || true
	done
	echo "tunnel-firewall: rules removed"
	;;
print)
	rules
	echo "# and, at the top of DOCKER-USER and INPUT: -s $TUNNEL_SUBNET -j DIXIE-TUNNEL / DIXIE-TUNNEL-HOST"
	;;
*)
	echo "usage: $0 apply|remove|print" >&2
	exit 2
	;;
esac
