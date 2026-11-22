#!/usr/bin/env bash
# The status report the `monitor` account prints, and the only thing it can
# do (decision 0128): sshd runs this as the account's forced command,
# whatever command the client asked for. It reads only what any user can
# read, plus the file dixie-monitor-snapshot.timer writes as root for the
# containers and the NVMe drive, so the account needs no sudo and no
# Docker. Changed only by tests: MONITOR_SNAPSHOT, REBOOT_REQUIRED.
set -uo pipefail

SNAPSHOT=${MONITOR_SNAPSHOT:-/var/lib/dixie-monitor/status}
REBOOT_REQUIRED=${REBOOT_REQUIRED:-/var/run/reboot-required}
STALE_MINUTES=15

section() { printf '\n== %s\n' "$1"; }

echo "Dixie Detail production host status, $(TZ=America/New_York date '+%F %H:%M %Z')"

section "Release and kernel"
# shellcheck source=/dev/null
[[ -r /etc/os-release ]] && . /etc/os-release && echo "Release: ${PRETTY_NAME:-unknown}"
echo "Kernel: $(uname -r)"
echo "Up: $(uptime -p 2>/dev/null || echo unknown)"

section "Pending updates"
upgradable=$(apt list --upgradable 2>/dev/null | grep -F '[upgradable from' || true)
echo "Pending: $(grep -c . <<<"$upgradable" || true), of which security: $(grep -c -- '-security' <<<"$upgradable" || true)"
[[ -z $upgradable ]] || sed 's/^/  /' <<<"$upgradable"

section "Reboot required"
if [[ -e $REBOOT_REQUIRED ]]; then
	echo "Yes, for: $(tr '\n' ' ' <"$REBOOT_REQUIRED.pkgs" 2>/dev/null || echo "(no package list)")"
else
	echo "No"
fi

section "Disk use"
df -h --output=target,size,used,avail,pcent / /srv /var 2>/dev/null | awk '!seen[$0]++'

section "Failed units"
failed=$(systemctl --failed --no-legend --plain 2>/dev/null)
echo "${failed:-None}"

section "Last backup runs"
for unit in dixie-backup dixie-backup-offsite dixie-offsite-prune; do
	systemctl show "$unit.service" -p ExecMainExitTimestamp -p Result -p ExecMainStatus 2>/dev/null |
		awk -v unit="$unit" -F= '{v[$1]=$2} END {printf "%-22s last ended %s, result %s, exit status %s\n", unit, (v["ExecMainExitTimestamp"] == "" ? "never" : v["ExecMainExitTimestamp"]), v["Result"], v["ExecMainStatus"]}'
done
systemctl list-timers --all --no-pager dixie-backup.timer dixie-backup-offsite.timer dixie-offsite-prune.timer 2>/dev/null | head -n 4

section "Containers and NVMe health"
if [[ -r $SNAPSHOT ]]; then
	age=$((($(date +%s) - $(stat -c %Y -- "$SNAPSHOT")) / 60))
	((age < STALE_MINUTES)) || echo "WARNING: this part is $age minutes old; dixie-monitor-snapshot.timer isn't running"
	cat -- "$SNAPSHOT"
else
	echo "Not written yet ($SNAPSHOT); dixie-monitor-snapshot.timer writes it every 5 minutes"
fi
