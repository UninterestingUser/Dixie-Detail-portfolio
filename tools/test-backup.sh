#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests ops/backup.sh (decision 0127) against fakes of restic, bws, docker,
# curl and sleep:
#   - the hourly run dumps once, keeps only the latest local dump, and sends
#     the dump and the photos to the backup server only, pinging
#     HEALTHCHECKS_BACKUP_URL;
#   - the nightly run also sends them to Backblaze B2, pinging
#     HEALTHCHECKS_OFFSITE_URL, each destination tried even when the other
#     fails;
#   - the 5- and 15-minute retries, and what isn't retried (a wrong
#     password, a refused rest-server password, a certificate restic won't
#     trust);
#   - nothing is pruned or deleted from the production host;
#   - an hourly run skips itself while the nightly run holds the lock.
# Needs bash, jq, coreutils and util-linux (flock); no restic, no network.
# Run by tools/run-tests.sh, or on its own:  tools/test-backup.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0
pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

mkdir -p "$work/fake"
# A fake restic. The destination is "rest" or "s3", from RESTIC_REPOSITORY;
# the command is backup, photos or the restic command. FAKE_FAIL_<dest>_<command>=N
# fails the first N such calls, with exit status FAKE_RC and the error
# FAKE_ERROR.
cat >"$work/fake/restic" <<'FAKE'
#!/usr/bin/env bash
dest=${RESTIC_REPOSITORY%%:*}
[[ $1 == --cacert ]] && { cacert=$2; shift 2; }
command=$1
[[ $1 == backup && " $* " == *" --tag photos "* ]] && command=photos
printf '%s|%s|%s|cacert=%s|user=%s|rest=%s|aws=%s:%s\n' "$dest" "$command" "$*" "${cacert:-}" "$RESTIC_REST_USERNAME" \
	"$RESTIC_REST_PASSWORD" "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" >>"$FAKE_DIR/restic-calls"
[[ $RESTIC_PASSWORD == made-up-password ]] || { echo "Fatal: wrong password or no key found" >&2; exit 12; }
key="${dest}_$command"
echo "$key" >>"$FAKE_DIR/commands"
n=$(grep -cx "$key" "$FAKE_DIR/commands")
[[ $command == backup ]] && echo "$(wc -c)" >>"$FAKE_DIR/stdin-bytes"
var="FAKE_FAIL_$key"
if ((n <= ${!var:-0})); then
	echo "Fatal: ${FAKE_ERROR:-made-up error} $key $n" >&2
	exit "${FAKE_RC:-1}"
fi
echo "made-up $command output"
FAKE
cat >"$work/fake/bws" <<'FAKE'
#!/usr/bin/env bash
jq -n '[{key:"RESTIC_PASSWORD",value:"made-up-password"},{key:"BACKUP_REST_PASSWORD",value:"made-up-rest"},
	{key:"B2_KEY_ID",value:"made-up-key-id"},{key:"B2_APPLICATION_KEY",value:"made-up-app-key"},
	{key:"HEALTHCHECKS_BACKUP_URL",value:"https://hc.example.invalid/ping/backup"},
	{key:"HEALTHCHECKS_OFFSITE_URL",value:"https://hc.example.invalid/ping/offsite"}]'
FAKE
cat >"$work/fake/docker" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >>"$FAKE_DIR/docker-calls"
case "$*" in
	*pg_dump*) [[ -z ${FAKE_DUMP_FAILS:-} ]] || exit 1; printf 'PGDMP made-up dump\n' ;;
	*pg_restore*) cat >/dev/null ;;
esac
FAKE
cat >"$work/fake/curl" <<'FAKE'
#!/usr/bin/env bash
url=$(sed -n 's/^url = "\(.*\)"$/\1/p')
echo "$url" >>"$FAKE_DIR/pings"
for arg; do [[ $arg != @* ]] || cp -- "${arg#@}" "$FAKE_DIR/ping-body-${url##*/}"; done
FAKE
printf '#!/bin/sh\necho "$1" >>"$FAKE_DIR/sleeps"\n' >"$work/fake/sleep"
chmod +x "$work/fake"/*

# run_backup MODE [VAR=VALUE...]: runs ops/backup.sh with the fakes and a
# fresh state; its output goes to $work/b/out. Prints its exit status.
run_backup() {
	local mode=$1
	shift
	rm -rf "$work/b"
	mkdir -p "$work/b/run" "$work/b/creds" "$work/b/photos" "$work/b/backups"
	printf 'made-up-token' >"$work/b/creds/bws-token"
	local rc=0
	env "$@" PATH="$work/fake:$PATH" FAKE_DIR="$work/b" RUNTIME_DIRECTORY="$work/b/run" \
		CREDENTIALS_DIRECTORY="$work/b/creds" BWS_SERVER_URL=https://vault.example.invalid \
		BWS_PROJECT_ID=made-up-project BACKUP_DIR="$work/b/backups" BACKUP_LOCK="$work/lock" \
		BACKUP_HOST_ADDRESS=192.0.2.20 BACKUP_REST_CACERT=/etc/dixie-detail/backup-server.pem \
		B2_REPOSITORY=s3:https://s3.us-west-004.backblazeb2.com/made-up-bucket/restic \
		POSTGRES_DB=dixie POSTGRES_USER=dixie QUOTE_PHOTO_HOST_DIR="$work/b/photos" \
		"$repo/ops/backup.sh" "$mode" >"$work/b/out" 2>&1 || rc=$?
	echo "$rc"
}
count() { if [[ -e $work/b/commands ]]; then grep -cx "$1" "$work/b/commands" || true; else echo 0; fi; }
sleeps() { tr '\n' ' ' 2>/dev/null <"$work/b/sleeps" | sed 's/ $//'; }
pings() { tr '\n' ' ' 2>/dev/null <"$work/b/pings" | sed 's|https://hc.example.invalid/ping/||g; s/ $//'; }

echo "test-backup: the hourly run goes to the backup server only"
rc=$(run_backup hourly)
[[ $rc == 0 ]] && pass "the run ends as a success" || fail "exit status $rc: $(tail -5 "$work/b/out")"
[[ $(count rest_backup) == 1 && $(count rest_photos) == 1 && $(count s3_backup) == 0 && $(count s3_photos) == 0 ]] &&
	pass "one dump upload and one photo upload, to the backup server" || fail "calls: $(tr '\n' ' ' <"$work/b/commands")"
grep -q '^rest|backup|backup --host dixie-detail --tag database --stdin --stdin-filename dixie-detail.dump|cacert=/etc/dixie-detail/backup-server.pem|user=dixie-detail|rest=made-up-rest|' "$work/b/restic-calls" &&
	pass "the dump goes with the pinned certificate and rest-server's password, tagged database" || fail "calls: $(cat "$work/b/restic-calls")"
grep -q "^rest|photos|backup --host dixie-detail --tag photos $work/b/photos|" "$work/b/restic-calls" &&
	pass "the photo folder goes tagged photos" || fail "calls: $(cat "$work/b/restic-calls")"
[[ $(pings) == "backup/start backup" ]] && pass "HEALTHCHECKS_BACKUP_URL gets the start and success pings, and nothing else" || fail "pings: $(pings)"
[[ $(sort -u "$work/b/stdin-bytes") == 19 ]] && pass "restic got the whole dump" || fail "bytes: $(cat "$work/b/stdin-bytes")"
[[ $(ls "$work/b/backups") == dixie-detail-latest.dump ]] && pass "only the latest dump is kept locally" || fail "kept: $(ls "$work/b/backups")"
! grep -qE '\|(forget|prune|delete|key)\|' "$work/b/restic-calls" && pass "nothing is pruned or deleted" || fail "calls: $(cat "$work/b/restic-calls")"
! grep -q 'aws=made-up' "$work/b/restic-calls" && pass "the B2 key is not even loaded for the hourly run" || fail "calls: $(cat "$work/b/restic-calls")"

echo "test-backup: the nightly run goes to both, each with its own ping"
rc=$(run_backup nightly)
[[ $rc == 0 ]] && pass "the run ends as a success" || fail "exit status $rc: $(tail -5 "$work/b/out")"
[[ $(count rest_backup) == 1 && $(count rest_photos) == 1 && $(count s3_backup) == 1 && $(count s3_photos) == 1 ]] &&
	pass "the dump and the photos go to the backup server, then to B2" || fail "calls: $(tr '\n' ' ' <"$work/b/commands")"
[[ $(grep -c pg_dump "$work/b/docker-calls") == 1 ]] && pass "the database is dumped once for both" || fail "dumped $(grep -c pg_dump "$work/b/docker-calls") times"
grep -q '^s3|backup|.*|cacert=|.*|aws=made-up-key-id:made-up-app-key$' "$work/b/restic-calls" &&
	pass "B2 gets its key in restic's environment, and no certificate pin" || fail "calls: $(cat "$work/b/restic-calls")"
[[ $(pings) == "backup/start backup offsite/start offsite" ]] && pass "each destination pings its own check" || fail "pings: $(pings)"

echo "test-backup: a failed B2 upload fails the run, not the backup server's part"
rc=$(run_backup nightly FAKE_FAIL_s3_backup=9)
[[ $rc != 0 && $(count rest_backup) == 1 && $(count s3_backup) == 3 && $(sleeps) == "300 900" ]] &&
	pass "three B2 attempts, 5 and 15 minutes apart; the run fails" || fail "status $rc, $(count s3_backup) B2 uploads, waits $(sleeps)"
[[ $(pings) == "backup/start backup offsite/start offsite/fail" ]] && pass "the backup server's check succeeds, the offsite check fails" || fail "pings: $(pings)"
for n in 1 2 3; do
	grep -q "upload to b2, attempt $n of 3" "$work/b/ping-body-fail" && grep -q "made-up error s3_backup $n" "$work/b/ping-body-fail" ||
		fail "attempt $n is missing from the ping's log"
done
[[ $(stat -c %s "$work/b/ping-body-fail") -le 10000 ]] && pass "the failure ping carries every attempt, within 10,000 bytes" || fail "ping body is $(stat -c %s "$work/b/ping-body-fail") bytes"

echo "test-backup: a failed backup server still lets B2 have tonight's backup"
rc=$(run_backup nightly FAKE_FAIL_rest_backup=9)
[[ $rc != 0 && $(count rest_backup) == 3 && $(count s3_backup) == 1 && $(count s3_photos) == 1 ]] &&
	pass "B2 is tried after the backup server gives up" || fail "status $rc, calls: $(tr '\n' ' ' <"$work/b/commands")"
[[ $(pings) == "backup/start backup/fail offsite/start offsite" ]] && pass "each check says how its own part went" || fail "pings: $(pings)"

echo "test-backup: retries"
rc=$(run_backup hourly FAKE_FAIL_rest_backup=1)
[[ $rc == 0 && $(count rest_backup) == 2 && $(sleeps) == 300 ]] && grep -q "upload to backup-server succeeded on attempt 2 of 3" "$work/b/out" &&
	pass "an upload that fails once is tried again 5 minutes later" || fail "status $rc, $(count rest_backup) uploads, waits $(sleeps)"
[[ $(sort -u "$work/b/stdin-bytes") == 19 ]] && pass "each attempt gets the whole dump" || fail "bytes: $(cat "$work/b/stdin-bytes")"
rc=$(run_backup hourly FAKE_FAIL_rest_photos=9)
[[ $rc != 0 && $(count rest_photos) == 1 && -z $(sleeps) ]] && pass "a photo upload gets one attempt" || fail "status $rc, $(count rest_photos) photo uploads, waits $(sleeps)"
rc=$(run_backup hourly FAKE_DUMP_FAILS=1)
[[ $rc != 0 && $(count rest_backup) == 0 && $(grep -c pg_dump "$work/b/docker-calls") == 1 ]] && [[ ! -e $work/b/backups/dixie-detail-latest.dump.partial ]] &&
	pass "a failed dump is not retried, sends nothing and leaves no partial file" || fail "status $rc"

echo "test-backup: what waiting can't fix is not retried"
for case in "12|wrong password or no key found" "1|unexpected HTTP response (401): 401 Unauthorized" "1|tls: failed to verify certificate: x509: certificate signed by unknown authority" "1|InvalidAccessKeyId"; do
	code=${case%%|*} error=${case#*|}
	rc=$(run_backup hourly FAKE_FAIL_rest_backup=9 FAKE_RC="$code" FAKE_ERROR="$error")
	[[ $rc == "$code" && $(count rest_backup) == 1 && -z $(sleeps) ]] && grep -q "upload to backup-server is not retried" "$work/b/ping-body-fail" &&
		pass "${error%%:*}: one attempt, no wait, failure ping" || fail "$error: status $rc, $(count rest_backup) uploads, waits $(sleeps)"
done

echo "test-backup: a held host isn't production yet, so it doesn't back up"
touch "$work/hold"
rc=$(run_backup hourly TUNNEL_HOLD="$work/hold")
[[ $rc == 0 && ! -s $work/b/commands && ! -e $work/b/docker-calls ]] && grep -q "this host isn't production yet" "$work/b/out" &&
	pass "while the tunnel is held, the backup skips: no dump, no snapshot" || fail "status $rc: $(cat "$work/b/out")"
rm -f "$work/hold"

echo "test-backup: one run at a time"
exec 8>"$work/lock"
flock 8
rc=$(run_backup hourly)
[[ $rc == 0 && ! -s $work/b/commands ]] && grep -q "nightly run is in progress" "$work/b/out" &&
	pass "an hourly run that finds the lock held skips itself" || fail "status $rc: $(cat "$work/b/out")"
exec 8>&-
rc=$(run_backup bogus)
[[ $rc == 2 ]] && pass "an unknown mode is refused" || fail "status $rc"

((failures == 0)) || { echo "test-backup: $failures failure(s)" >&2; exit 1; }
echo "test-backup: PASS"
