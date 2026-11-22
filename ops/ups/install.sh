#!/usr/bin/env bash
# Installs the apcupsd configuration for this host's role (decision 0128).
# Run as root, once on each host, and again after a change here:
#
#   sudo /srv/dixie-detail/ops/ups/install.sh production    # the host with the USB cable
#   sudo /srv/dixie-detail/ops/ups/install.sh backup-host   # the network client
#
# Checks that Ubuntu's shutdown hook, which switches the UPS off after the
# production host's shutdown, is in place, then restarts apcupsd and shows
# its status. Changed only by tests: APCUPSD_DIR, SHUTDOWN_HOOK.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
APCUPSD_DIR=${APCUPSD_DIR:-/etc/apcupsd}
SHUTDOWN_HOOK=${SHUTDOWN_HOOK:-/usr/lib/systemd/system-shutdown/apcupsd_shutdown}
# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "ups: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=../lib/settings.sh
. ops/lib/settings.sh
fail() { echo "ups: FAIL: $*" >&2; exit 1; }

role=${1:-}
case $role in
	production) source=ops/ups/apcupsd-production.conf ;;
	backup-host) source=ops/ups/apcupsd-backup-host.conf ;;
	*) echo "usage: install.sh production|backup-host" >&2; exit 2 ;;
esac
command -v apcupsd >/dev/null || fail "apcupsd isn't installed: sudo apt install apcupsd"

if [[ $role == production ]]; then
	# Without this hook the UPS keeps its outlets on after the shutdown, and
	# a host that shut down while mains power came back would stay off.
	[[ -x $SHUTDOWN_HOOK ]] && grep -q 'apccontrol killpower' "$SHUTDOWN_HOOK" ||
		fail "$SHUTDOWN_HOOK is missing or doesn't run apccontrol killpower; see docs/operations/building-the-production-host.md"
	install -m 0644 "$source" "$APCUPSD_DIR/apcupsd.conf"
	nis=localhost:3551
else
	address=$(setting PRODUCTION_HOST_ADDRESS)
	[[ $address =~ ^[0-9]+(\.[0-9]+){3}$ ]] || fail "set PRODUCTION_HOST_ADDRESS in .env to the production host's LAN address"
	sed "s/^DEVICE PRODUCTION_HOST_ADDRESS:3551$/DEVICE $address:3551/" "$source" >"$APCUPSD_DIR/apcupsd.conf.new"
	grep -q "^DEVICE $address:3551$" "$APCUPSD_DIR/apcupsd.conf.new" || fail "couldn't set the production host's address"
	chmod 0644 "$APCUPSD_DIR/apcupsd.conf.new"
	mv -f "$APCUPSD_DIR/apcupsd.conf.new" "$APCUPSD_DIR/apcupsd.conf"
	# This host serves no status of its own: ask the production host's.
	nis=$address:3551
fi
systemctl enable --quiet apcupsd.service
systemctl restart apcupsd.service
sleep 5
apcaccess status "$nis" | grep -E '^(UPSNAME|MODEL|STATUS|BCHARGE|TIMELEFT|MBATTCHG|MINTIMEL|MAXTIME|DSHUTD|DWAKE|RETPCT) ' || true
echo "ups: installed the $role configuration"
