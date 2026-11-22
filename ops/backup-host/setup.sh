#!/usr/bin/env bash
# Installs and starts the backup server on the backup host (decision 0127):
# restic's rest-server in Docker, append-only, with private repositories, a
# password (BACKUP_REST_PASSWORD) and TLS with a self-signed certificate,
# listening on BACKUP_HOST_ADDRESS:BACKUP_REST_PORT, its data in
# BACKUP_REST_DATA_DIR on the RAID. Also creates the repository (its one key
# labeled restic/restic) and installs the weekly prune and restore test.
# Run on the backup host as root, after credentials.sh:
#
#   sudo /srv/dixie-detail/ops/backup-host/setup.sh
#   sudo /srv/dixie-detail/ops/backup-host/setup.sh --new-password   # after rotating BACKUP_REST_PASSWORD
#
# It asks for BACKUP_REST_PASSWORD once, pasted from Bitwarden and never
# shown, and stores only its bcrypt hash. Running it again changes nothing
# that is already in place. It ends by printing the certificate the
# production host pins, and its fingerprint.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
CONFIG_DIR=${REST_CONFIG_DIR:-/etc/dixie-rest-server}
UNIT_DIR=${SYSTEMD_UNIT_DIR:-/etc/systemd/system}
CERT_DAYS=3650

# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "setup: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=../lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=../lib/restic.sh
. ops/lib/restic.sh

new_password=false
[[ ${1:-} != --new-password ]] || new_password=true
fail() { echo "setup: FAIL: $*" >&2; exit 1; }

restic_settings_from_env_file
: "${BACKUP_HOST_ADDRESS:?set BACKUP_HOST_ADDRESS in .env}" "${BACKUP_REST_DATA_DIR:?set BACKUP_REST_DATA_DIR in .env}"
image=$(sed -n 's/^ *image: *//p' ops/backup-host/compose.yaml | head -1)
for tool in docker restic openssl jq setpriv systemd-creds; do
	command -v "$tool" >/dev/null || fail "$tool is missing (docs/operations/setting-up-the-backup-host.md)"
done
gnu_timeout >/dev/null || exit 1
[[ -f $HOST_CRED_DIR/dixie-restic-password.cred ]] || fail "run ops/backup-host/credentials.sh first"
mountpoint -q /mnt/raid || fail "/mnt/raid is not mounted"

# rest-server's user, which owns the repository's files.
getent passwd "$REST_SERVER_UID" >/dev/null ||
	useradd --system --uid "$REST_SERVER_UID" --user-group --no-create-home --shell /usr/sbin/nologin dixie-rest-server
install -d -m 0700 -o "$REST_SERVER_UID" -g "$REST_SERVER_UID" "$BACKUP_REST_DATA_DIR" "$RESTIC_LOCAL_CACHE"
install -d -m 0750 -o root -g "$REST_SERVER_UID" "$CONFIG_DIR"

# The certificate, for the backup host's LAN address, which the production
# host's restic pins with --cacert. Ten years: a new one means copying it to
# the production host again.
if [[ ! -f $CONFIG_DIR/cert.pem ]]; then
	(
		umask 027
		openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days "$CERT_DAYS" \
			-subj "/CN=dixie-backup-server" -addext "subjectAltName=IP:$BACKUP_HOST_ADDRESS" \
			-keyout "$CONFIG_DIR/key.pem" -out "$CONFIG_DIR/cert.pem" 2>/dev/null
	)
	chgrp "$REST_SERVER_UID" "$CONFIG_DIR/key.pem"
	chmod 0640 "$CONFIG_DIR/key.pem"
	chmod 0644 "$CONFIG_DIR/cert.pem"
	echo "setup: made a certificate for $BACKUP_HOST_ADDRESS"
fi
openssl x509 -in "$CONFIG_DIR/cert.pem" -noout -checkend 2592000 >/dev/null ||
	echo "setup: WARNING: the certificate expires within 30 days; move it aside and run this again" >&2

# The password's bcrypt hash only. htpasswd reads the password on its stdin.
if [[ ! -s $CONFIG_DIR/htpasswd ]] || $new_password; then
	read -rsp "Paste BACKUP_REST_PASSWORD from Bitwarden (it won't be shown), then press Enter: " password <"${DIXIE_TTY:-/dev/tty}"
	echo >&2
	[[ -n $password ]] || fail "the password was empty"
	hash=$(printf '%s' "$password" | docker run --rm -i --network none --entrypoint htpasswd "$image" -niBC 10 "$REST_USER")
	unset password
	[[ $hash == "$REST_USER:\$2"* ]] || fail "htpasswd didn't make a bcrypt hash"
	(umask 027 && printf '%s\n' "$hash" >"$CONFIG_DIR/htpasswd.new")
	chgrp "$REST_SERVER_UID" "$CONFIG_DIR/htpasswd.new"
	mv -f "$CONFIG_DIR/htpasswd.new" "$CONFIG_DIR/htpasswd"
	unset hash
	echo "setup: stored the hash of BACKUP_REST_PASSWORD (never the password)"
fi

# The repository, created here (not through the append-only server) so its
# first key can be swapped for one labeled restic/restic.
restic_use local
restic_password=$(host_credential restic-password)
restic_init_labeled
unset restic_password

# The units. Nothing here is ever installed on the production host.
for unit in ops/backup-host/*.service ops/backup-host/*.timer; do
	install -m 0644 "$unit" "$UNIT_DIR/"
done
systemctl daemon-reload
systemctl enable --quiet dixie-rest-server.service dixie-backup-host-weekly.timer
systemctl restart dixie-rest-server.service
systemctl start dixie-backup-host-weekly.timer
docker compose --env-file "$DIXIE_DIR/.env" -f ops/backup-host/compose.yaml ps

echo
echo "setup: the backup server listens on https://$BACKUP_HOST_ADDRESS:${BACKUP_REST_PORT:-8443}/$REST_USER/"
echo "Copy this certificate to the production host as the file BACKUP_REST_CACERT names"
echo "(docs/operations/setting-up-the-backup-host.md). It isn't secret."
cat "$CONFIG_DIR/cert.pem"
openssl x509 -in "$CONFIG_DIR/cert.pem" -noout -fingerprint -sha256
