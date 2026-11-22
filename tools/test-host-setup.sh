#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests the production host's setup scripts (decision 0128) against fakes,
# in a throwaway copy of ops/:
#   - host-firewall.sh: SSH and the control app over Tailscale, apcupsd from
#     the backup host only, nothing else in; check fails on any other rule;
#   - the UPS: the production host shuts down at 20% or 5 minutes left and
#     serves port 3551; the backup host is a network client that shuts down
#     after 2 minutes; install.sh refuses a production host whose apcupsd
#     package wouldn't switch the UPS off. With APCUPSD_PACKAGE_CHECK=1 (the
#     Tests workflow's Ubuntu 26.04 job) it also downloads Ubuntu's apcupsd
#     package and checks its shutdown hook;
#   - the monitor account: key only, no sudo or docker group, a forced
#     command in a root-owned authorized_keys; its report has every part;
#   - site-mode.sh passes only requests or normal to the app.
# The scripts that check for root are run with DIXIE_EUID=0, as this user.
# Needs bash, coreutils and util-linux; no network unless asked.
# Run by tools/run-tests.sh, or on its own:  tools/test-host-setup.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0
pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

mkdir -p "$work/bin" "$work/dixie"
cp -r "$repo/ops" "$work/dixie/"
printf 'BACKUP_HOST_ADDRESS=192.0.2.20\nPRODUCTION_HOST_ADDRESS=192.0.2.30\n' >"$work/dixie/.env"
export FAKE_LOG="$work/log"
printf '#!/usr/bin/env bash\necho "systemctl $*" >>"$FAKE_LOG"\nexit 0\n' >"$work/bin/systemctl"
printf '#!/usr/bin/env bash\nexit 0\n' >"$work/bin/sleep"
chmod +x "$work/bin/"*
run() { : >"$FAKE_LOG"; env DIXIE_EUID=0 PATH="$work/bin:$PATH" DIXIE_DIR="$work/dixie" "$@" >"$work/out" 2>&1; }

# --------------------------------------------------------------- firewall
echo "test-host-setup: the production host's firewall"
# A fake ufw: logs each call; `status verbose` prints FAKE_UFW_STATUS.
cat >"$work/bin/ufw" <<'FAKE'
#!/usr/bin/env bash
echo "ufw $*" >>"$FAKE_LOG"
[[ $1 == status ]] && cat "$FAKE_UFW_STATUS"
exit 0
FAKE
chmod +x "$work/bin/ufw"
cat >"$work/status" <<'STATUS'
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), deny (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
22/tcp on tailscale0       ALLOW IN    Anywhere                   # dixie: SSH over Tailscale
443/tcp on tailscale0      ALLOW IN    Anywhere                   # dixie: control app (tailscale serve)
3551/tcp                   ALLOW IN    192.0.2.20                 # dixie: apcupsd for the backup host
22/tcp (v6) on tailscale0  ALLOW IN    Anywhere (v6)              # dixie: SSH over Tailscale
443/tcp (v6) on tailscale0 ALLOW IN    Anywhere (v6)              # dixie: control app (tailscale serve)
STATUS
run FAKE_UFW_STATUS="$work/status" "$work/dixie/ops/host-firewall.sh" apply && grep -q "host-firewall: PASS" "$work/out" &&
	pass "apply sets the rules and its check passes" || fail "said: $(cat "$work/out")"
expected="ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0 to any port 22 proto tcp comment dixie: SSH over Tailscale
ufw allow in on tailscale0 to any port 443 proto tcp comment dixie: control app (tailscale serve)
ufw allow in proto tcp from 192.0.2.20 to any port 3551 comment dixie: apcupsd for the backup host
ufw --force enable"
[[ $(grep '^ufw' "$FAKE_LOG" | grep -v '^ufw status') == "$expected" ]] &&
	pass "deny in by default; SSH and 443 on tailscale0; 3551 from the backup host only" || fail "calls: $(cat "$FAKE_LOG")"
grep -q "^systemctl restart dixie-tunnel-firewall.service" "$FAKE_LOG" && pass "the tunnel's rules are put back after" || fail "calls: $(cat "$FAKE_LOG")"
sed '/^3551/a 8080/tcp                   ALLOW IN    Anywhere' "$work/status" >"$work/status-extra"
run FAKE_UFW_STATUS="$work/status-extra" "$work/dixie/ops/host-firewall.sh" check && fail "an extra rule passed" ||
	{ grep -q "4 rules, expected 3" "$work/out" && pass "check fails on a rule that shouldn't be there"; } || fail "said: $(cat "$work/out")"
sed 's/^Status: active/Status: inactive/' "$work/status" >"$work/status-off"
run FAKE_UFW_STATUS="$work/status-off" "$work/dixie/ops/host-firewall.sh" check && fail "an inactive firewall passed" || pass "check fails when ufw is off"

# -------------------------------------------------------------------- UPS
echo "test-host-setup: the UPS on two hosts"
conf="$repo/ops/ups/apcupsd-production.conf"
value() { sed -n "s/^$2 //p" "$1"; }
[[ $(value "$conf" UPSCABLE) == usb && $(value "$conf" BATTERYLEVEL) == 20 && $(value "$conf" MINUTES) == 5 && $(value "$conf" TIMEOUT) == 0 ]] &&
	pass "production: USB, shuts down at 20% or 5 minutes left" || fail "production's levels are wrong"
[[ $(value "$conf" NETSERVER) == on && $(value "$conf" NISPORT) == 3551 && $(value "$conf" PWRFAILDIR) == /etc/apcupsd ]] &&
	pass "production: serves port 3551, and writes the powerfail flag where Ubuntu's shutdown hook looks" || fail "production's server lines are wrong"
client="$repo/ops/ups/apcupsd-backup-host.conf"
[[ $(value "$client" UPSTYPE) == net && $(value "$client" TIMEOUT) == 120 && $(value "$client" NETSERVER) == off ]] &&
	pass "backup host: a network client that shuts down after 2 minutes on battery" || fail "the backup host's lines are wrong"
for tool in apcupsd apcaccess; do printf '#!/usr/bin/env bash\necho "%s $*" >>"$FAKE_LOG"\n' "$tool" >"$work/bin/$tool"; done
chmod +x "$work/bin/"*
mkdir -p "$work/apcupsd"
printf '#!/bin/sh\nif [ -f /etc/apcupsd/powerfail ]; then\n  /etc/apcupsd/apccontrol killpower\nfi\n' >"$work/hook"
chmod +x "$work/hook"
run APCUPSD_DIR="$work/apcupsd" SHUTDOWN_HOOK="$work/hook" "$work/dixie/ops/ups/install.sh" production &&
	cmp -s "$work/apcupsd/apcupsd.conf" "$conf" && grep -q "^systemctl restart apcupsd.service" "$FAKE_LOG" &&
	pass "production: installed and restarted" || fail "said: $(cat "$work/out")"
run APCUPSD_DIR="$work/apcupsd" SHUTDOWN_HOOK="$work/no-hook" "$work/dixie/ops/ups/install.sh" production && fail "installed without the hook" ||
	{ grep -q "doesn't run apccontrol killpower" "$work/out" && pass "production: refused when the shutdown hook wouldn't switch the UPS off"; } || fail "said: $(cat "$work/out")"
run APCUPSD_DIR="$work/apcupsd" "$work/dixie/ops/ups/install.sh" backup-host && grep -qx "DEVICE 192.0.2.30:3551" "$work/apcupsd/apcupsd.conf" &&
	grep -q "^apcaccess status 192.0.2.30:3551" "$FAKE_LOG" && pass "backup host: points at PRODUCTION_HOST_ADDRESS" || fail "said: $(cat "$work/out")"
if [[ ${APCUPSD_PACKAGE_CHECK:-} == 1 ]]; then
	(cd "$work" && apt-get download -q apcupsd >/dev/null 2>&1 && dpkg-deb -x apcupsd_*.deb pkg) || fail "couldn't download Ubuntu's apcupsd package"
	hook="$work/pkg/usr/lib/systemd/system-shutdown/apcupsd_shutdown"
	[[ -x $hook ]] && grep -q 'apccontrol killpower' "$hook" && grep -q 'powerfail' "$hook" &&
		pass "this release's apcupsd package has the shutdown hook that switches the UPS off ($(dpkg-deb -f "$work"/apcupsd_*.deb Version))" ||
		fail "this release's apcupsd package has no killpower shutdown hook"
fi

# ---------------------------------------------------------------- monitor
echo "test-host-setup: the monitor account"
ssh-keygen -q -t ed25519 -N "" -C made-up-assistant -f "$work/key" >/dev/null
for tool in useradd passwd gpasswd sshd; do printf '#!/usr/bin/env bash\necho "%s $*" >>"$FAKE_LOG"\n' "$tool" >"$work/bin/$tool"; done
# id: the account exists, in the docker and sudo groups until removed.
printf '#!/usr/bin/env bash\n[[ $1 == -nG ]] && { echo "monitor docker sudo"; exit 0; }\nexit 0\n' >"$work/bin/id"
# sshd -T: what the drop-in forces.
printf '#!/usr/bin/env bash\necho "sshd $*" >>"$FAKE_LOG"\n[[ $1 == -T ]] && echo "forcecommand /srv/dixie-detail/ops/monitor/status.sh"\nexit 0\n' >"$work/bin/sshd"
# install: do the work, ignoring the owners a normal user can't set.
cat >"$work/bin/install" <<'FAKE'
#!/usr/bin/env bash
args=()
while (($#)); do case $1 in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac; done
exec /usr/bin/install "${args[@]}"
FAKE
chmod +x "$work/bin/"*
mkdir -p "$work/sshd"
setup() { run SSHD_DIR="$work/sshd" MONITOR_KEYS_DIR="$work/keys" "$work/dixie/ops/monitor/setup.sh" "$@"; }
setup "$work/key.pub" && pass "setup succeeds" || fail "said: $(cat "$work/out")"
line=$(cat "$work/keys/authorized_keys" 2>/dev/null)
[[ $line == "restrict,command=\"/srv/dixie-detail/ops/monitor/status.sh\" ssh-ed25519 "*" made-up-assistant" ]] &&
	pass "the key's line: restrict, and the status report as its forced command" || fail "authorized_keys: $line"
grep -q "^passwd --lock monitor" "$FAKE_LOG" && grep -q "^gpasswd --delete monitor docker" "$FAKE_LOG" && grep -q "^gpasswd --delete monitor sudo" "$FAKE_LOG" &&
	pass "no password, and out of the docker and sudo groups" || fail "log: $(cat "$FAKE_LOG")"
drop="$work/sshd/50-dixie-monitor.conf"
grep -qx "Match User monitor" "$drop" && grep -q "ForceCommand /srv/dixie-detail/ops/monitor/status.sh" "$drop" && grep -q "PasswordAuthentication no" "$drop" &&
	grep -q "AuthenticationMethods publickey" "$drop" && grep -q "PermitTTY no" "$drop" && [[ $(tail -1 "$drop") == "Match all" ]] &&
	pass "sshd forces the same command, key only, no terminal, and ends its Match block" || fail "drop-in: $(cat "$drop")"
grep -q "^sshd -t" "$FAKE_LOG" && grep -q "^systemctl reload ssh.service" "$FAKE_LOG" && pass "sshd checks the configuration before reloading" || fail "log: $(cat "$FAKE_LOG")"
setup "$work/key" && fail "a private key was accepted" || pass "a private key is refused"
# The report, with fakes for what it reads.
cat >"$work/bin/apt" <<'FAKE'
#!/usr/bin/env bash
echo "Listing..."
echo "openssl/resolute-security 3.5.4-1ubuntu1.1 amd64 [upgradable from: 3.5.4-1ubuntu1]"
echo "tzdata/resolute-updates 2026c-1 all [upgradable from: 2026b-1]"
FAKE
printf '#!/usr/bin/env bash\ncase $1 in --failed) echo "dixie-backup.service loaded failed failed Dixie Detail hourly backup";; show) printf "ExecMainExitTimestamp=Sun 2026-11-22 10:06:01 EST\\nResult=success\\nExecMainStatus=0\\n";; *) echo "NEXT LEFT";; esac\n' >"$work/bin/systemctl"
chmod +x "$work/bin/"*
printf 'Written: 2026-11-22 10:05 EST\nContainers (service, state, health, status):\n  app\trunning\thealthy\tUp 2 hours\n' >"$work/snapshot"
touch "$work/reboot-required"
printf 'linux-image-7.0.0-12-generic\n' >"$work/reboot-required.pkgs"
PATH="$work/bin:$PATH" MONITOR_SNAPSHOT="$work/snapshot" REBOOT_REQUIRED="$work/reboot-required" "$repo/ops/monitor/status.sh" >"$work/report" 2>&1
for part in "Release and kernel" "Kernel: " "Pending: 2, of which security: 1" "Yes, for: linux-image-7.0.0-12-generic" "Disk use" \
	"dixie-backup.service loaded failed" "dixie-backup-offsite" "last ended Sun 2026-11-22 10:06:01 EST, result success" "app	running	healthy"; do
	grep -qF "$part" "$work/report" || fail "the report lacks: $part"
done
pass "the report has release and kernel, updates, reboot, disk, failed units, backups and containers"
touch -d "1 hour ago" "$work/snapshot"
report=$(PATH="$work/bin:$PATH" MONITOR_SNAPSHOT="$work/snapshot" "$repo/ops/monitor/status.sh")
grep -q "WARNING: this part is 6[0-9] minutes old" <<<"$report" &&
	pass "an old snapshot is flagged" || fail "no warning for an old snapshot"
! grep -vE '^[[:space:]]*#' "$repo/ops/monitor/status.sh" | grep -qE 'sudo|docker' && pass "the report never needs sudo or Docker" || fail "status.sh calls sudo or docker"

# -------------------------------------------------------------- site mode
echo "test-host-setup: site-mode.sh"
printf '#!/usr/bin/env bash\necho "docker $*" >>"$FAKE_LOG"\n' >"$work/bin/docker"
chmod +x "$work/bin/docker"
run "$work/dixie/ops/site-mode.sh" requests "moving to the new host" &&
	grep -qx "docker compose exec -T app python manage.py site_mode requests --reason moving to the new host" "$FAKE_LOG" &&
	pass "requests mode, with its reason, goes to the app's site_mode command" || fail "log: $(cat "$FAKE_LOG")"
run "$work/dixie/ops/site-mode.sh" normal && grep -q "site_mode normal" "$FAKE_LOG" && pass "normal" || fail "log: $(cat "$FAKE_LOG")"
run "$work/dixie/ops/site-mode.sh" && grep -qx "docker compose exec -T app python manage.py site_mode" "$FAKE_LOG" && pass "no argument shows the mode" || fail "log: $(cat "$FAKE_LOG")"
run "$work/dixie/ops/site-mode.sh" off && fail "an unknown mode was passed on" || pass "an unknown mode is refused"

((failures == 0)) || { echo "test-host-setup: $failures failure(s)" >&2; exit 1; }
echo "test-host-setup: PASS"
