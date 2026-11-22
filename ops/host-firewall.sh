#!/usr/bin/env bash
# The production host's own firewall (decision 0128), with ufw:
#   - SSH only over Tailscale (port 22 on tailscale0), and the control app's
#     tailscale serve port (443 on tailscale0);
#   - apcupsd's port 3551 only from the backup host (BACKUP_HOST_ADDRESS);
#   - nothing else in. Everything out is allowed; pfSense limits where the
#     production host's network may go.
# Tailscale's own netfilter rules accept tailnet traffic before ufw sees it,
# so the tailnet policy (docs/operations/tailscale-policy.md) decides who on
# the tailnet reaches the host; these rules close the LAN side. Docker's
# published ports are on 127.0.0.1 only, and the tunnel network has its own
# rules (ops/tunnel-firewall.sh, decision 0125). Run as root:
#
#   sudo /srv/dixie-detail/ops/host-firewall.sh apply
#   sudo /srv/dixie-detail/ops/host-firewall.sh check
#
# apply resets ufw to exactly these rules (any rule added by hand is
# removed), enables it, and puts the tunnel's rules back. UFW is changed
# only by tests.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
UFW=${UFW:-ufw}
# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "host-firewall: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/settings.sh
. ops/lib/settings.sh

backup_host=$(setting BACKUP_HOST_ADDRESS)
[[ $backup_host =~ ^[0-9]+(\.[0-9]+){3}$ ]] || { echo "host-firewall: set BACKUP_HOST_ADDRESS in .env" >&2; exit 1; }

# The rules, as `ufw status` prints them (To, Action, From), for check.
expected=(
	"22/tcp on tailscale0|ALLOW IN|Anywhere"
	"443/tcp on tailscale0|ALLOW IN|Anywhere"
	"3551/tcp|ALLOW IN|$backup_host"
)

apply() {
	"$UFW" --force reset >/dev/null
	"$UFW" default deny incoming
	"$UFW" default allow outgoing
	"$UFW" allow in on tailscale0 to any port 22 proto tcp comment "dixie: SSH over Tailscale"
	"$UFW" allow in on tailscale0 to any port 443 proto tcp comment "dixie: control app (tailscale serve)"
	"$UFW" allow in proto tcp from "$backup_host" to any port 3551 comment "dixie: apcupsd for the backup host"
	"$UFW" --force enable
	# ufw's reset and enable rebuild only ufw's own chains; put the tunnel's
	# jump back at the top of INPUT anyway.
	if systemctl is-enabled --quiet dixie-tunnel-firewall.service 2>/dev/null; then
		systemctl restart dixie-tunnel-firewall.service
	fi
	check
}

check() {
	local status rules rule ok=1 count
	status=$("$UFW" status verbose)
	grep -q '^Status: active' <<<"$status" || { echo "host-firewall: FAIL: ufw isn't active" >&2; ok=0; }
	grep -q 'Default: deny (incoming)' <<<"$status" || { echo "host-firewall: FAIL: incoming isn't denied by default" >&2; ok=0; }
	# The IPv4 rules, one "To|Action|From" a line, with ufw's columns of
	# spaces folded and the comments dropped.
	rules=$(sed -n '/^--/,$p' <<<"$status" | sed '1d' | grep -v '(v6)' | sed -E 's/ +#.*$//; s/ +$//; s/  +/|/g' | sed '/^$/d')
	for rule in "${expected[@]}"; do
		grep -qxF "$rule" <<<"$rules" || { echo "host-firewall: FAIL: missing rule: ${rule//|/  }" >&2; ok=0; }
	done
	count=$(grep -c . <<<"$rules" || true)
	((count == ${#expected[@]})) || { echo "host-firewall: FAIL: $count rules, expected ${#expected[@]}:" >&2; echo "$rules" >&2; ok=0; }
	((ok)) || return 1
	echo "host-firewall: PASS: ufw allows only SSH and the control app over Tailscale, and apcupsd from $backup_host"
}

case ${1:-} in
	apply) apply ;;
	check) check ;;
	*) echo "usage: host-firewall.sh apply|check" >&2; exit 2 ;;
esac
