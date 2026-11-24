#!/usr/bin/env bash
# Stores the backup host's two secrets as systemd credentials (decision
# 0126). The backup host has no Bitwarden machine account, so it can never
# read the production secrets; it keeps only these two, each encrypted with
# systemd-creds (the host key, plus the TPM when the host has a usable one,
# decision 0130) and never in plain text:
#   RESTIC_PASSWORD               for the weekly prune and restore test
#   HEALTHCHECKS_BACKUP_HOST_URL  the weekly job's Healthchecks ping URL
# Run on the backup host as root. It asks for each value, pasted from the
# owner's Bitwarden (project "Dixie Detail"), and never shows or logs it.
# Run it again after a rotation; with a name it asks for that one only:
#
#   sudo /srv/dixie-detail/ops/backup-host/credentials.sh
#   sudo /srv/dixie-detail/ops/backup-host/credentials.sh RESTIC_PASSWORD
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
# DIXIE_EUID is set only by the tests, which run as a normal user.
[[ ${DIXIE_EUID:-$EUID} -eq 0 ]] || { echo "credentials: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=../lib/bws.sh
. ops/lib/bws.sh
# shellcheck source=../lib/restic.sh
. ops/lib/restic.sh

names=("$@")
((${#names[@]})) || names=(RESTIC_PASSWORD HEALTHCHECKS_BACKUP_HOST_URL)

# ask NAME: reads a pasted value into $value, without echoing it.
ask() {
	value=""
	read -rsp "Paste $1 from Bitwarden (it won't be shown), then press Enter: " value <"${DIXIE_TTY:-/dev/tty}"
	echo >&2
	[[ -n $value ]] || { echo "credentials: $1 was empty; nothing stored" >&2; return 1; }
}

for name in "${names[@]}"; do
	case $name in
		RESTIC_PASSWORD) cred=restic-password ;;
		HEALTHCHECKS_BACKUP_HOST_URL) cred=healthchecks-backup-host-url ;;
		*) echo "credentials: unknown name $name (RESTIC_PASSWORD or HEALTHCHECKS_BACKUP_HOST_URL)" >&2; exit 2 ;;
	esac
	ask "$name"
	if [[ $name == RESTIC_PASSWORD ]]; then
		# A typo would lock the weekly job out: check the password against the
		# repository when there is one, or have it pasted twice.
		restic_settings_from_env_file
		restic_use local
		restic_password=$value
		if [[ -f $restic_repository/config ]]; then
			run_restic cat config >/dev/null 2>&1 ||
				{ echo "credentials: that password doesn't open $restic_repository; nothing stored" >&2; exit 1; }
			echo "credentials: the password opens the backup server's repository"
		else
			first=$value
			ask "$name again"
			[[ $value == "$first" ]] || { echo "credentials: the two didn't match; nothing stored" >&2; exit 1; }
			unset first
		fi
		unset restic_password
	elif [[ $value != https://* ]]; then
		echo "credentials: $name should start with https://; nothing stored" >&2
		exit 1
	fi
	install -d -m 0700 "$HOST_CRED_DIR"
	printf '%s' "$value" | systemd-creds encrypt --with-key=auto --name="$cred" - "$HOST_CRED_DIR/dixie-$cred.cred"
	chmod 0600 "$HOST_CRED_DIR/dixie-$cred.cred"
	unset value
	echo "credentials: stored $name as $HOST_CRED_DIR/dixie-$cred.cred (encrypted with this host's key, and its TPM if it has a usable one)"
done
