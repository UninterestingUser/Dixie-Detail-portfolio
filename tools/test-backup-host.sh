#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file. The
# scripts in single quotes run in a child bash, so they must not expand here.
# shellcheck disable=SC2015,SC2016
# Tests the backup host's scripts and the backups' other ends (decisions
# 0126 and 0127) against fakes, in a throwaway copy of ops/:
#   - the B2 bucket check passes a bucket of restic's files only, across
#     pages, and fails on anything else, with the key never on a command line;
#   - offsite-prune.sh keeps 14 daily and 12 monthly on B2 and runs the check;
#   - credentials.sh stores the two secrets with systemd-creds, never on a
#     command line, and refuses a password that doesn't open the repository;
#   - setup.sh stores only the hash of BACKUP_REST_PASSWORD, makes the
#     certificate for the backup host's address, and creates the repository;
#   - weekly.sh prunes to 48 hourly, 14 daily and 12 monthly, checks, runs
#     the restore test and pings its check;
#   - restore.sh refuses a database with data unless told, and restores the
#     dump and the photos into a fresh stack.
# The scripts that check for root are run with DIXIE_EUID=0, as this user,
# with fakes for what only root may do. Needs bash, jq, openssl, coreutils and
# util-linux; no restic, Docker, network or real secret.
# Run by tools/run-tests.sh, or on its own:  tools/test-backup-host.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0
pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }
as_root() { env DIXIE_EUID=0 "$@"; }

mkdir -p "$work/bin" "$work/dixie" "$work/creds"
cp -r "$repo/ops" "$repo/compose.yaml" "$work/dixie/"
export FAKE_LOG="$work/log" FAKE_KEYS="$work/keys.json"
hex() { printf '%064d' "$1" | tr 0-9 a-j | tr g-j 0-3; }

# ---------------------------------------------------------------- B2 check
echo "test-backup-host: the B2 bucket holds only restic's repository"
# A fake curl serving ListObjectsV2 pages from $FAKE_PAGES/page-N.xml,
# N from the continuation token; it logs its command line and its config.
cat >"$work/bin/curl" <<'FAKE'
#!/usr/bin/env bash
echo "curl $*" >>"$FAKE_LOG"
config=$(cat)
printf '%s\n' "$config" >>"$FAKE_LOG.config"
[[ -z ${FAKE_CURL_FAILS:-} ]] || { echo "curl: (22) The requested URL returned error: 403" >&2; exit 22; }
token=$(sed -n 's/.*continuation-token=\([^"&]*\).*/\1/p' <<<"$config")
cat "$FAKE_PAGES/page-${token:-1}.xml"
FAKE
chmod +x "$work/bin/curl"
mkdir -p "$work/pages"
page() { # N NEXT FILES...
	local n=$1 next=$2 f
	shift 2
	{
		echo '<?xml version="1.0" encoding="UTF-8"?><ListBucketResult>'
		for f; do echo "<Contents><Key>$f</Key><Size>10</Size></Contents>"; done
		if [[ -n $next ]]; then echo "<IsTruncated>true</IsTruncated><NextContinuationToken>$next</NextContinuationToken>"; else echo "<IsTruncated>false</IsTruncated>"; fi
		echo '</ListBucketResult>'
	} >"$work/pages/page-$n.xml"
}
b2_check() {
	: >"$FAKE_LOG"
	: >"$FAKE_LOG.config"
	PATH="$work/bin:$PATH" FAKE_PAGES="$work/pages" bash -c '
		set -euo pipefail
		cd "$1"; . ops/lib/restic.sh; . ops/lib/b2.sh
		B2_REPOSITORY=s3:https://s3.us-west-004.backblazeb2.com/made-up-bucket/restic
		b2_key_id=made-up-key-id b2_application_key=made-up-app-key
		b2_check_only_repository_files
	' _ "$work/dixie" >"$work/out" 2>&1
}
page 1 2 restic/config "restic/keys/$(hex 1)" "restic/data/ab/$(hex 2)"
page 2 "" "restic/index/$(hex 3)" "restic/snapshots/$(hex 4)" "restic/locks/$(hex 5)"
b2_check && grep -q "all 6 file(s) in the bucket made-up-bucket are restic's encrypted repository" "$work/out" &&
	pass "a bucket of repository files passes, across two pages" || fail "said: $(cat "$work/out")"
grep -q 'aws-sigv4 = "aws:amz:us-west-004:s3"' "$FAKE_LOG.config" && grep -q 'url = "https://s3.us-west-004.backblazeb2.com/made-up-bucket?list-type=2' "$FAKE_LOG.config" &&
	pass "listed through B2's S3 API, signed for the bucket's region" || fail "config: $(cat "$FAKE_LOG.config")"
! grep -q made-up "$FAKE_LOG" && pass "the key is never on curl's command line" || fail "argv: $(cat "$FAKE_LOG")"
page 2 "" "restic/index/$(hex 3)" "customer-list.csv"
b2_check && fail "a file outside the repository passed" ||
	{ grep -q "customer-list.csv is outside the repository's folder restic/" "$work/out" && pass "a file outside the repository fails, by name"; } || fail "said: $(cat "$work/out")"
page 2 "" "restic/index/$(hex 3)" "restic/data/ab/dixie-detail.dump"
b2_check && fail "a plain dump inside the folder passed" ||
	{ grep -q "restic/data/ab/dixie-detail.dump isn't a restic repository file" "$work/out" && pass "a file restic didn't name fails, by name"; } || fail "said: $(cat "$work/out")"
FAKE_CURL_FAILS=1 b2_check && fail "a failed listing passed" || pass "a listing that fails fails the check"

# ---------------------------------------------------------- offsite prune
echo "test-backup-host: offsite-prune.sh prunes B2 and checks the bucket"
page 1 "" restic/config "restic/keys/$(hex 1)"
cat >"$work/bin/restic" <<'FAKE'
#!/usr/bin/env bash
[[ $1 == --cacert ]] && shift 2
echo "restic $*|repo=$RESTIC_REPOSITORY|password=$RESTIC_PASSWORD" >>"$FAKE_LOG"
case $1 in
	cat) [[ -e ${FAKE_REPO_DIR:-/nonexistent}/config && $RESTIC_PASSWORD == made-up-password ]] ;;
	snapshots)
		case "$*" in
			*"--path /dixie-detail.dump"*) echo '[{"short_id":"db000001","time":"2026-11-22T10:05:00-05:00"}]' ;;
			*) echo '[{"short_id":"ph000001","time":"2026-11-22T10:05:01-05:00"}]' ;;
		esac ;;
	dump) printf 'PGDMP made-up\n' ;;
	restore) mkdir -p "$4$FAKE_PHOTOS" && touch "$4$FAKE_PHOTOS/made-up-photo.jpg" ;;
	init) echo '[{"id":"aaaa","userName":"root","hostName":"backup"}]' >"$FAKE_KEYS" ;;
	key)
		case $2 in
			list) cat "$FAKE_KEYS" ;;
			add) [[ $(cat) == "$RESTIC_PASSWORD" ]] && jq '. + [{id:"bbbb",userName:"restic",hostName:"restic"}]' "$FAKE_KEYS" >"$FAKE_KEYS.new" && mv "$FAKE_KEYS.new" "$FAKE_KEYS" ;;
			remove) jq --arg id "${@: -1}" 'map(select(.id != $id))' "$FAKE_KEYS" >"$FAKE_KEYS.new" && mv "$FAKE_KEYS.new" "$FAKE_KEYS" ;;
		esac ;;
	forget|check) exit "${FAKE_RESTIC_RC:-0}" ;;
esac
FAKE
cat >"$work/bin/bws" <<'FAKE'
#!/usr/bin/env bash
jq -n '[{key:"RESTIC_PASSWORD",value:"made-up-password"},{key:"BACKUP_REST_PASSWORD",value:"made-up-rest"},
	{key:"B2_KEY_ID",value:"made-up-key-id"},{key:"B2_APPLICATION_KEY",value:"made-up-app-key"},
	{key:"HEALTHCHECKS_OFFSITE_URL",value:"https://hc.example.invalid/ping/offsite"}]'
FAKE
cat >"$work/bin/systemd-creds" <<'FAKE'
#!/usr/bin/env bash
echo "systemd-creds $*" >>"$FAKE_LOG"
case $1 in
	decrypt) name=${2#--name=}; [[ $name == bws-token ]] && { echo made-up-token; exit 0; }
		cat "${3%.cred}.plain" ;;
	encrypt) cat >"${@: -1}" ;;
esac
FAKE
# setpriv: run the command as this user (the test can't switch users).
printf '#!/usr/bin/env bash\nwhile [[ $1 == --* ]]; do shift; done\nexec "$@"\n' >"$work/bin/setpriv"
chmod +x "$work/bin/"*
cat >"$work/dixie/.env" <<'ENV'
BWS_PROJECT_ID=made-up-project
BWS_SERVER_URL=https://vault.example.invalid
POSTGRES_DB=dixie
POSTGRES_USER=dixie
BACKUP_HOST_ADDRESS=192.0.2.20
BACKUP_REST_CACERT=/etc/dixie-detail/backup-server.pem
B2_REPOSITORY=s3:https://s3.us-west-004.backblazeb2.com/made-up-bucket/restic
ENV
printf 'made-up-token' >"$work/creds/bws-token"
prune() {
	: >"$FAKE_LOG"
	rm -rf "$work/run" && mkdir -p "$work/run"
	(cd "$work/dixie" && set -a && . ./.env && set +a &&
		PATH="$work/bin:$PATH" FAKE_PAGES="$work/pages" RUNTIME_DIRECTORY="$work/run" CREDENTIALS_DIRECTORY="$work/creds" \
		ops/offsite-prune.sh) >"$work/out" 2>&1
}
prune && pass "the prune succeeds" || fail "said: $(cat "$work/out")"
grep -q '^restic forget --host dixie-detail --group-by host,paths --keep-daily 14 --keep-monthly 12 --prune --retry-lock 30m|repo=s3:' "$FAKE_LOG" &&
	pass "B2 keeps 14 daily and 12 monthly, the dumps and the photos each on their own" || fail "log: $(cat "$FAKE_LOG")"
grep -q "are restic's encrypted repository" "$work/out" && pass "the bucket check runs after the prune" || fail "said: $(cat "$work/out")"
page 1 "" restic/config notes.txt
prune && fail "a stray file passed" || { grep -q "url = \"https://hc.example.invalid/ping/offsite/fail\"" "$FAKE_LOG.config" && pass "a stray file in the bucket fails the run and pings the offsite check's /fail"; } || fail "config: $(cat "$FAKE_LOG.config")"

# ------------------------------------------------------------ credentials
echo "test-backup-host: credentials.sh keeps the backup host's two secrets encrypted"
mkdir -p "$work/backup-host" "$work/raid"
cp -r "$repo/ops" "$repo/compose.yaml" "$work/backup-host/"
printf 'BACKUP_HOST_ADDRESS=192.0.2.20\nBACKUP_REST_DATA_DIR=%s\n' "$work/raid" >"$work/backup-host/.env"
creds() { # VALUE NAME...
	local value=$1
	shift
	: >"$FAKE_LOG"
	printf '%s\n' "$value" >"$work/tty"
	PATH="$work/bin:$PATH" DIXIE_DIR="$work/backup-host" HOST_CRED_DIR="$work/credstore" DIXIE_TTY="$work/tty" \
		FAKE_REPO_DIR="$work/raid/dixie-detail" as_root "$work/backup-host/ops/backup-host/credentials.sh" "$@" >"$work/out" 2>&1
}
creds https://hc.example.invalid/ping/made-up-host HEALTHCHECKS_BACKUP_HOST_URL &&
	[[ $(cat "$work/credstore/dixie-healthchecks-backup-host-url.cred") == https://hc.example.invalid/ping/made-up-host ]] &&
	grep -q "systemd-creds encrypt --with-key=auto --name=healthchecks-backup-host-url - $work/credstore/dixie-healthchecks-backup-host-url.cred" "$FAKE_LOG" &&
	pass "the ping URL is encrypted, with the TPM only where there is one" || fail "said: $(cat "$work/out") log: $(cat "$FAKE_LOG")"
creds made-up-password RESTIC_PASSWORD && [[ $(cat "$work/credstore/dixie-restic-password.cred") == made-up-password ]] &&
	pass "with no repository yet, the password is asked for twice and stored" || fail "said: $(cat "$work/out")"
! grep -q 'made-up-password\|made-up-host' "$FAKE_LOG" && ! grep -q 'made-up-password' "$work/out" &&
	pass "neither value is on a command line or shown" || fail "log: $(cat "$FAKE_LOG")"
mkdir -p "$work/raid/dixie-detail" && touch "$work/raid/dixie-detail/config"
creds wrong-password RESTIC_PASSWORD && fail "a wrong password was stored" ||
	{ grep -q "that password doesn't open" "$work/out" && [[ $(cat "$work/credstore/dixie-restic-password.cred") == made-up-password ]] &&
		pass "a password that doesn't open the repository is refused, and the old one kept"; } || fail "said: $(cat "$work/out")"
creds made-up-password RESTIC_PASSWORD && grep -q "opens the backup server's repository" "$work/out" &&
	pass "the right one is checked against the repository and stored" || fail "said: $(cat "$work/out")"
creds http://not-https HEALTHCHECKS_BACKUP_HOST_URL && fail "a non-https URL was stored" || pass "a ping URL that isn't https is refused"
grep -q 'LoadCredentialEncrypted=restic-password:/etc/credstore.encrypted/dixie-restic-password.cred' "$repo/ops/backup-host/dixie-backup-host-weekly.service" &&
	! grep -q 'bws-token' "$repo/ops/backup-host/dixie-backup-host-weekly.service" &&
	pass "the weekly unit loads the two credentials and no Bitwarden token" || fail "the weekly unit's credentials are wrong"

# ------------------------------------------------------------------ setup
echo "test-backup-host: setup.sh stores only the password's hash, and makes the certificate and the repository"
rm -rf "$work/raid/dixie-detail"
cat >"$work/bin/docker" <<'FAKE'
#!/usr/bin/env bash
echo "docker $*" >>"$FAKE_LOG"
if [[ " $* " == *" --entrypoint htpasswd "* ]]; then
	read -r password
	[[ $password == made-up-rest ]] || exit 1
	echo 'dixie-detail:$2y$10$madeuphashmadeuphashmadeuphashmadeuphashmadeuphash12'
fi
exit 0
FAKE
for tool in mountpoint useradd systemctl install chgrp; do printf '#!/usr/bin/env bash\necho "%s $*" >>"$FAKE_LOG"\n' "$tool" >"$work/bin/$tool"; done
# install -d / -m: do the work, ignoring owners this namespace can't set.
cat >"$work/bin/install" <<'FAKE'
#!/usr/bin/env bash
echo "install $*" >>"$FAKE_LOG"
args=()
while (($#)); do case $1 in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac; done
exec /usr/bin/install "${args[@]}"
FAKE
printf '#!/usr/bin/env bash\nexit 0\n' >"$work/bin/getent"
chmod +x "$work/bin/"*
setup() {
	: >"$FAKE_LOG"
	printf 'made-up-rest\n' >"$work/tty"
	PATH="$work/bin:$PATH" DIXIE_DIR="$work/backup-host" HOST_CRED_DIR="$work/credstore" DIXIE_TTY="$work/tty" \
		REST_CONFIG_DIR="$work/rest-config" RESTIC_LOCAL_CACHE="$work/cache" SYSTEMD_UNIT_DIR="$work/units" FAKE_REPO_DIR="$work/raid/dixie-detail" \
		as_root "$work/backup-host/ops/backup-host/setup.sh" >"$work/out" 2>&1
}
cp "$work/credstore/dixie-restic-password.cred" "$work/credstore/dixie-restic-password.plain"
mkdir -p "$work/units"
setup && pass "setup succeeds" || fail "said: $(cat "$work/out")"
[[ $(cat "$work/rest-config/htpasswd" 2>/dev/null) == 'dixie-detail:$2y$10$'* ]] && ! grep -rq made-up-rest "$work/rest-config" "$FAKE_LOG" &&
	pass "only the bcrypt hash is stored, and the password is never on a command line" || fail "htpasswd: $(cat "$work/rest-config/htpasswd" 2>/dev/null)"
openssl x509 -in "$work/rest-config/cert.pem" -noout -ext subjectAltName 2>/dev/null | grep -q "IP Address:192.0.2.20" &&
	pass "the certificate is for the backup host's address" || fail "certificate: $(openssl x509 -in "$work/rest-config/cert.pem" -noout -text 2>&1 | head -5)"
grep -q "^restic init|repo=$work/raid/dixie-detail" "$FAKE_LOG" && grep -q "^restic key add --host restic --user restic" "$FAKE_LOG" &&
	pass "the repository is created on the RAID, its key relabeled restic/restic" || fail "log: $(grep restic "$FAKE_LOG")"
[[ -f $work/units/dixie-rest-server.service && -f $work/units/dixie-backup-host-weekly.timer && ! -e $work/units/dixie-backup.service ]] &&
	pass "only the backup host's units are installed" || fail "units: $(ls "$work/units")"
grep -q "BEGIN CERTIFICATE" "$work/out" && grep -qi "SHA256 Fingerprint=" "$work/out" && pass "it prints the certificate to copy, and its fingerprint" || fail "said: $(cat "$work/out")"
before=$(cat "$work/rest-config/htpasswd")
setup && [[ $(cat "$work/rest-config/htpasswd") == "$before" ]] && ! grep -q "entrypoint htpasswd" "$FAKE_LOG" &&
	pass "a second run asks for nothing and changes nothing" || fail "said: $(cat "$work/out")"
compose="$repo/ops/backup-host/compose.yaml"
grep -q -- "--append-only" "$compose" && grep -q -- "--private-repos" "$compose" && grep -q -- "--tls$" "$compose" && grep -q 'user: "10010:10010"' "$compose" &&
	grep -q 'BACKUP_HOST_ADDRESS:?' "$compose" && grep -q 'BACKUP_REST_PORT:-8443' "$compose" &&
	pass "rest-server runs append-only, private, over TLS, as its own user, on the LAN address only" || fail "compose.yaml lacks an option"

# ----------------------------------------------------------------- weekly
echo "test-backup-host: weekly.sh prunes, checks and restore-tests the backup server's repository"
printf 'https://hc.example.invalid/ping/backup-host' >"$work/creds/healthchecks-backup-host-url"
printf 'made-up-password' >"$work/creds/restic-password"
printf '#!/usr/bin/env bash\necho "restore-test $*" >>"$FAKE_LOG"\nexit "${FAKE_RESTORE_RC:-0}"\n' >"$work/backup-host/ops/restore-test.sh"
weekly() {
	: >"$FAKE_LOG"
	: >"$FAKE_LOG.config"
	rm -rf "$work/run" && mkdir -p "$work/run"
	(cd "$work/backup-host" && set -a && . ./.env && set +a &&
		env "$@" PATH="$work/bin:$PATH" RUNTIME_DIRECTORY="$work/run" CREDENTIALS_DIRECTORY="$work/creds" ops/backup-host/weekly.sh) >"$work/out" 2>&1
}
weekly && pass "the weekly job succeeds" || fail "said: $(cat "$work/out")"
grep -q "^restic forget --host dixie-detail --group-by host,paths --keep-hourly 48 --keep-daily 14 --keep-monthly 12 --prune --retry-lock 30m|repo=$work/raid/dixie-detail|password=made-up-password" "$FAKE_LOG" &&
	pass "48 hourly, 14 daily and 12 monthly, read from the RAID with the host's own password" || fail "log: $(cat "$FAKE_LOG")"
grep -q "^restic check --read-data-subset 5%" "$FAKE_LOG" && grep -qx "restore-test --repo local" "$FAKE_LOG" &&
	pass "then a check and the restore test from the local repository" || fail "log: $(cat "$FAKE_LOG")"
[[ $(sed -n 's/^url = "\(.*\)"$/\1/p' "$FAKE_LOG.config" | tr '\n' ' ') == "https://hc.example.invalid/ping/backup-host/start https://hc.example.invalid/ping/backup-host " ]] &&
	pass "HEALTHCHECKS_BACKUP_HOST_URL gets the start and success pings" || fail "pings: $(cat "$FAKE_LOG.config")"
weekly FAKE_RESTORE_RC=1 && fail "a failed restore test passed" ||
	{ grep -q 'ping/backup-host/fail' "$FAKE_LOG.config" && pass "a failed restore test fails the job and pings /fail"; } || fail "pings: $(cat "$FAKE_LOG.config")"
! grep -q 'bws' "$FAKE_LOG" && pass "the backup host never calls Bitwarden" || fail "log: $(cat "$FAKE_LOG")"

# ---------------------------------------------------------------- restore
echo "test-backup-host: restore.sh restores a fresh stack, and refuses one with data"
cat >"$work/bin/docker" <<'FAKE'
#!/usr/bin/env bash
echo "docker $*" >>"$FAKE_LOG"
case "$*" in
	*psql*"auth_user) + "*) echo "${FAKE_EXISTING:-0}" ;;
	*psql*pg_tables*) echo 60 ;;
	*psql*customers_customer*) echo 12 ;;
	*"pg_restore --list"*) cat >/dev/null ;;
	*pg_restore*) cat >"$FAKE_DIR/restored" ;;
esac
exit 0
FAKE
printf '#!/usr/bin/env bash\necho "systemctl $*" >>"$FAKE_LOG"\n[[ $1 != is-active || -z ${FAKE_STOPPED:-} ]]\n' >"$work/bin/systemctl"
printf '#!/usr/bin/env bash\necho "rsync $*" >>"$FAKE_LOG"\ncp -r "${@: -2:1}." "${@: -1}"\n' >"$work/bin/rsync"
printf '#!/usr/bin/env bash\necho "chown $*" >>"$FAKE_LOG"\n' >"$work/bin/chown"
chmod +x "$work/bin/"*
restore() {
	: >"$FAKE_LOG"
	rm -rf "$work/srv" && mkdir -p "$work/srv"
	# shellcheck disable=SC2086 # RESTORE_ARGS is split on purpose
	as_root env PATH="$work/bin:$PATH" DIXIE_DIR="$work/dixie" BWS_TOKEN_CRED="$work/creds/bws-token" FAKE_DIR="$work" \
		QUOTE_PHOTO_HOST_DIR="$work/srv/photos" FAKE_PHOTOS="$work/srv/photos" "$@" \
		"$work/dixie/ops/restore.sh" ${RESTORE_ARGS:-} >"$work/out" 2>&1
}
restore FAKE_EXISTING=3 && fail "it restored over existing data" ||
	{ grep -q "already has 3 customer(s) and user(s)" "$work/out" && ! grep -qE "pg_restore -U|compose stop" "$FAKE_LOG" &&
		pass "a database with customers or users is refused, untouched"; } || fail "said: $(cat "$work/out")"
restore FAKE_STOPPED=1 && fail "it ran with the stack stopped" || pass "it refuses when dixie-stack.service isn't running"
rm -f "$work/restored"
restore && pass "a fresh stack is restored" || fail "said: $(cat "$work/out")"
[[ $(cat "$work/restored" 2>/dev/null) == "PGDMP made-up" ]] && grep -q "pg_restore -U dixie -d dixie --clean --if-exists --no-owner --single-transaction --exit-on-error" "$FAKE_LOG" &&
	pass "the newest dump is loaded in one transaction" || fail "log: $(cat "$FAKE_LOG")"
grep -q "^docker compose stop app public calendar-worker photo-worker caddy cloudflared" "$FAKE_LOG" &&
	[[ $(grep -n "compose stop" "$FAKE_LOG" | cut -d: -f1) -lt $(grep -n "pg_restore -U" "$FAKE_LOG" | cut -d: -f1) ]] &&
	pass "everything but the database is stopped first" || fail "log: $(cat "$FAKE_LOG")"
[[ -f $work/srv/photos/made-up-photo.jpg ]] && grep -q "restic restore ph000001 --target $work/srv/dixie-photo-restore" "$FAKE_LOG" &&
	pass "the newest photo snapshot is written back to the photo folder" || fail "photos: $(ls -R "$work/srv" 2>&1)"
[[ -z $(find "$work/srv" -maxdepth 1 -name 'dixie-photo-restore.*') ]] && pass "the staging folder is removed" || fail "left: $(ls "$work/srv")"
grep -q "^systemctl restart dixie-stack.service" "$FAKE_LOG" && grep -q "restore: done: 60 tables, 12 customer(s), from backup-server snapshot db000001" "$work/out" &&
	pass "the stack is restarted and the result shown" || fail "said: $(cat "$work/out")"
RESTORE_ARGS=--over-existing-data restore FAKE_EXISTING=3 && pass "with --over-existing-data it goes ahead" || fail "said: $(cat "$work/out")"

((failures == 0)) || { echo "test-backup-host: $failures failure(s)" >&2; exit 1; }
echo "test-backup-host: PASS"
