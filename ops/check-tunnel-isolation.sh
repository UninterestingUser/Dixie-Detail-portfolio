#!/usr/bin/env bash
# Checks the tunnel network's firewall (decision 0125) with real traffic: a
# throwaway container on the tunnel network, as cloudflared is, must reach
# Caddy's public door and a public internet address, and must NOT reach
# Caddy's control-app door, the host (through the network's gateway and
# through its LAN address) or another address on the LAN. Run on the server
# as root, with the stack running:
#
#   sudo /srv/dixie-detail/ops/check-tunnel-isolation.sh
#
# A refusal only proves something if the port is open, so each blocked
# target is first checked from the host itself; one that's closed there too
# is reported as not tested, not as passed. Uses Caddy's image (busybox nc
# and wget) with public DNS, as cloudflared has. Ends with
# "check-tunnel-isolation: PASS" or exits 1.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
[[ $EUID -eq 0 ]] || { echo "check-tunnel-isolation: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/settings.sh
. ops/lib/settings.sh

network=dixie_tunnel
caddy=172.31.250.20
image=$(docker compose config --format json | jq -r .services.caddy.image)
gateway=$(docker network inspect -f '{{(index .IPAM.Config 0).Gateway}}' "$network")
host_lan=$(ip -4 route get 1.1.1.1 | sed -n 's/.* src \([0-9.]*\).*/\1/p')
router=$(ip -4 route show default | sed -n 's/^default via \([0-9.]*\).*/\1/p' | head -1)
public_host=$(setting PUBLIC_HEALTH_URL | sed -E 's|^https?://([^/]+).*|\1|')
failures=0
pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

# in_tunnel COMMAND: runs a busybox command in a throwaway container on the
# tunnel network; its exit status is the command's.
in_tunnel() {
	docker run --rm --network "$network" --dns 1.1.1.1 --dns 1.0.0.1 --entrypoint sh "$image" -c "$1" >/dev/null 2>&1
}
# open_from_host HOST PORT: true when the port answers from the host itself.
open_from_host() {
	timeout 5 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null
}
# refused NAME HOST PORT
refused() {
	if ! open_from_host "$2" "$3"; then
		echo "  not tested: $1 ($2:$3) is closed from the host too"
		return
	fi
	if in_tunnel "nc -w 3 $2 $3 </dev/null"; then
		fail "$1 ($2:$3) is reachable from the tunnel network"
	else
		pass "$1 ($2:$3) is refused"
	fi
}

echo "Tunnel network $network: gateway $gateway; host's LAN address $host_lan; router $router"

echo "Must be reachable:"
if in_tunnel "wget -q -O- -T 10 --header 'Host: $public_host' http://$caddy:8080/health | grep -q '\"ok\"'"; then
	pass "Caddy's public door ($caddy:8080/health) answers ok"
else
	fail "Caddy's public door ($caddy:8080/health) doesn't answer"
fi
if in_tunnel "nc -w 5 1.1.1.1 443 </dev/null"; then pass "a public internet address (1.1.1.1:443)"; else fail "a public internet address (1.1.1.1:443) is unreachable"; fi
if in_tunnel "nslookup cloudflare.com >/dev/null"; then pass "public DNS"; else fail "public DNS doesn't resolve"; fi

echo "Must be refused:"
# Caddy's control-app door: refused by the firewall (and by Caddy itself).
if in_tunnel "wget -q -O /dev/null -T 5 http://$caddy:8000/"; then
	fail "Caddy's control-app door ($caddy:8000) is reachable from the tunnel network"
else
	pass "Caddy's control-app door ($caddy:8000) is refused"
fi
refused "the host through the gateway" "$gateway" 22
refused "the host's LAN address" "$host_lan" 22
refused "the host's LAN address, another service" "$host_lan" 8080
[[ -z $router ]] || refused "the LAN's router" "$router" 53
[[ -z $router ]] || refused "the LAN's router, web" "$router" 443

if ((failures)); then
	echo "check-tunnel-isolation: $failures FAILED; see docs/operations/troubleshooting.md" >&2
	exit 1
fi
echo "check-tunnel-isolation: PASS"
