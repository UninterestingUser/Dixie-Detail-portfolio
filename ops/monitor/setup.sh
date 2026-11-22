#!/usr/bin/env bash
# Creates the `monitor` account for the owner's maintenance assistant
# (decision 0128): SSH key only, no sudo, not in the docker group, and a
# forced command, so the key can print the status report (status.sh) and
# do nothing else. Run on the production host as root, with the assistant's
# public key (not a secret):
#
#   sudo /srv/dixie-detail/ops/monitor/setup.sh /path/to/monitor-key.pub
#
# Running it again replaces the key. The key's line in authorized_keys is
#   restrict,command="/srv/dixie-detail/ops/monitor/status.sh" ssh-ed25519 ...
# in a root-owned file the account can't change, and an sshd drop-in forces
# the same command and turns off passwords for the account. Changed only by
# tests: SSHD_DIR, MONITOR_KEYS_DIR.
set -euo pipefail

SSHD_DIR=${SSHD_DIR:-/etc/ssh/sshd_config.d}
KEYS_DIR=${MONITOR_KEYS_DIR:-/etc/ssh/dixie-monitor}
STATUS=/srv/dixie-detail/ops/monitor/status.sh
ACCOUNT=monitor
# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "monitor: run as root (sudo)" >&2; exit 1; }
fail() { echo "monitor: FAIL: $*" >&2; exit 1; }

key_file=${1:-}
[[ -r $key_file ]] || { echo "usage: setup.sh PUBLIC_KEY_FILE" >&2; exit 2; }
[[ $(grep -c . "$key_file") == 1 ]] || fail "$key_file should hold exactly one public key"
key=$(grep . "$key_file")
[[ $key =~ ^(ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ssh-rsa)\ [A-Za-z0-9+/=]+( .*)?$ ]] || fail "$key_file isn't an OpenSSH public key"
ssh-keygen -lf "$key_file" >/dev/null || fail "ssh-keygen can't read $key_file"
[[ $key != *PRIVATE* ]] || fail "that is a private key; never copy it to the server"

if ! id "$ACCOUNT" >/dev/null 2>&1; then
	useradd --create-home --shell /bin/bash --comment "Dixie Detail status reports" "$ACCOUNT"
fi
# No password at all: key only.
passwd --lock "$ACCOUNT" >/dev/null
for group in sudo admin docker adm lxd; do
	if id -nG "$ACCOUNT" | tr ' ' '\n' | grep -qx "$group"; then gpasswd --delete "$ACCOUNT" "$group" >/dev/null; fi
done

install -d -m 0755 -o root -g root "$KEYS_DIR"
printf 'restrict,command="%s" %s\n' "$STATUS" "$key" >"$KEYS_DIR/authorized_keys.new"
chmod 0644 "$KEYS_DIR/authorized_keys.new"
mv -f "$KEYS_DIR/authorized_keys.new" "$KEYS_DIR/authorized_keys"

cat >"$SSHD_DIR/50-dixie-monitor.conf" <<CONF
# The monitor account (decision 0128), written by ops/monitor/setup.sh.
Match User $ACCOUNT
	AuthorizedKeysFile $KEYS_DIR/authorized_keys
	AuthenticationMethods publickey
	PasswordAuthentication no
	KbdInteractiveAuthentication no
	ForceCommand $STATUS
	PermitTTY no
	AllowTcpForwarding no
	AllowStreamLocalForwarding no
	AllowAgentForwarding no
	X11Forwarding no
	PermitTunnel no
	PermitUserRC no
# Ends the Match block, so nothing after this file falls into it.
Match all
CONF
chmod 0644 "$SSHD_DIR/50-dixie-monitor.conf"
sshd -t || fail "sshd rejects the configuration; nothing reloaded"
systemctl reload ssh.service
sshd -T -C "user=$ACCOUNT,host=check,addr=100.64.0.1" | grep -qi "^forcecommand $STATUS$" ||
	fail "sshd doesn't force the status command for $ACCOUNT"
echo "monitor: the $ACCOUNT account can sign in with $(ssh-keygen -lf "$key_file" | cut -d' ' -f2) and only print the status report"
