#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests ops/tunnel-firewall.sh (decision 0125) with the real iptables, in a
# network namespace of its own (unshare -rn), so the host's firewall is never
# touched: the rules go in as written, in the right order, applying twice
# adds no second jump, and remove takes everything out. Where an unprivileged
# namespace isn't allowed, the same checks run against a fake iptables that
# records its calls. Behavior on the server, with real packets, is checked
# by ops/check-tunnel-isolation.sh.
# Run by tools/run-tests.sh, or on its own:  tools/test-tunnel-firewall.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0
pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

script="$repo/ops/tunnel-firewall.sh"

# A run in a namespace of its own: creates Docker's DOCKER-USER chain as
# Docker would, then runs the given steps and prints the rules.
inside() {
	unshare -rn bash -c '
		set -e
		iptables -N DOCKER-USER
		iptables -A FORWARD -j DOCKER-USER
		for step in "$@"; do "$0" "$step" >/dev/null; done
		iptables -S
	' "$script" "$@"
}

if command -v iptables >/dev/null && unshare -rn iptables -S >/dev/null 2>&1; then
	echo "test-tunnel-firewall: the real iptables, in a namespace of its own"
	rules=$(inside apply)
	order=$(grep -E '^-A DIXIE-TUNNEL ' <<<"$rules" | sed 's/^-A DIXIE-TUNNEL //')
	[[ $(sed -n 1p <<<"$order") == *"ESTABLISHED"*"RETURN"* ]] && pass "replies come first" || fail "first rule: $(sed -n 1p <<<"$order")"
	[[ $(sed -n 2p <<<"$order") == "-d 172.31.250.20/32 -p tcp -m tcp --dport 8080 -j RETURN" ]] && pass "Caddy's public door is allowed before any drop" || fail "second rule: $(sed -n 2p <<<"$order")"
	for range in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16; do
		grep -qx -- "-d $range -j DROP" <<<"$order" && pass "drops $range" || fail "no drop for $range"
	done
	[[ $(tail -1 <<<"$order") == "-j RETURN" ]] && pass "public addresses go on to Docker's own rules" || fail "last rule: $(tail -1 <<<"$order")"
	grep -qx -- "-A DIXIE-TUNNEL-HOST -j DROP" <<<"$rules" && pass "the host's own addresses are dropped (INPUT)" || fail "no host drop"
	twice=$(inside apply apply)
	[[ $(grep -c -- "-A DOCKER-USER -s 172.31.250.0/24 -j DIXIE-TUNNEL" <<<"$twice") == 1 && $(grep -c -- "-A INPUT -s 172.31.250.0/24 -j DIXIE-TUNNEL-HOST" <<<"$twice") == 1 ]] &&
		pass "applying twice keeps one jump in each of DOCKER-USER and INPUT" || fail "jumps after two applies: $(grep -- '-j DIXIE' <<<"$twice")"
	[[ $(grep -c -- "-A DIXIE-TUNNEL " <<<"$twice") == $(grep -c -- "-A DIXIE-TUNNEL " <<<"$rules") ]] && pass "applying twice doesn't double the rules" || fail "rules doubled"
	[[ $(sed -n 1p < <(grep -- "-A DOCKER-USER" <<<"$twice")) == *"-j DIXIE-TUNNEL" ]] && pass "the jump is at the top of DOCKER-USER" || fail "DOCKER-USER: $(grep -- '-A DOCKER-USER' <<<"$twice")"
	removed=$(inside apply remove)
	! grep -q "DIXIE" <<<"$removed" && pass "remove takes out both chains and both jumps" || fail "left after remove: $(grep DIXIE <<<"$removed")"
	missing=$(unshare -rn "$script" apply 2>&1) && fail "applied without DOCKER-USER" ||
		{ grep -q "DOCKER-USER chain is missing" <<<"$missing" && pass "without Docker's chain it stops with a message" || fail "said: $missing"; }
else
	echo "test-tunnel-firewall: no unprivileged namespace here; checking with a fake iptables"
	cat >"$work/iptables" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >>"$FAKE_LOG"
[[ $1 == -C ]] && exit 1
exit 0
FAKE
	cat >"$work/iptables-restore" <<'FAKE'
#!/usr/bin/env bash
cat >>"$FAKE_RESTORE"
FAKE
	chmod +x "$work/iptables" "$work/iptables-restore"
	FAKE_LOG="$work/log" FAKE_RESTORE="$work/restore" IPTABLES="$work/iptables" "$script" apply >/dev/null
	grep -q -- "-d 172.31.250.20/32 -p tcp -m tcp --dport 8080 -j RETURN" "$work/restore" && pass "the rules reach iptables-restore" || fail "restore got: $(cat "$work/restore")"
	grep -q -- "-I DOCKER-USER 1 -s 172.31.250.0/24 -j DIXIE-TUNNEL" "$work/log" && grep -q -- "-I INPUT 1 -s 172.31.250.0/24 -j DIXIE-TUNNEL-HOST" "$work/log" &&
		pass "both jumps are inserted at the top" || fail "calls: $(cat "$work/log")"
fi

# The script's addresses match compose.yaml's.
grep -q "subnet: 172.31.250.0/24" "$repo/compose.yaml" && grep -q "ipv4_address: 172.31.250.20" "$repo/compose.yaml" &&
	pass "the tunnel subnet and Caddy's address match compose.yaml" || fail "compose.yaml's tunnel addresses differ from the script's"

if ((failures)); then
	echo "test-tunnel-firewall: $failures FAILED" >&2
	exit 1
fi
echo "test-tunnel-firewall: PASS"
