#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file. The
# scripts in single quotes run in a child bash, so they must not expand here.
# shellcheck disable=SC2015,SC2016
# Tests ops/lib/restic.sh and ops/lib/errors.sh against a fake restic that,
# like the real one, locks the repository while it works and leaves the lock
# behind when it is killed. Reproduces the 2026-11-03 incident: a reader that
# stopped early cut restic off mid-dump, the restore test quit without a
# message, and the stale lock failed every backup until `restic unlock`.
# Also runs ops/backup.sh against fakes of restic, bws, docker and curl to
# test its retries of a slow Google Drive (decision 0089).
# Needs bash, coreutils and jq; no restic, no repository and no real secret.
# Run by tools/run-tests.sh, or on its own:  tools/test-restic.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0

pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

# A fake restic. Each command takes a lock named after its PID in
# $FAKE_REPO/locks and removes it when it finishes; a locked repository
# fails as restic 0.17 does, with exit status 11. `dump` writes a 1 MiB
# "archive", far more than a pipe holds, so a reader that stops early
# kills it with SIGPIPE before it can remove its lock. `unlock` removes
# locks whose process is gone, as restic does.
mkdir -p "$work/bin" "$work/repo/locks"
cat >"$work/bin/restic" <<'FAKE'
#!/usr/bin/env bash
locks="$FAKE_REPO/locks"
printf '%s|tps=%s\n' "$*" "${RCLONE_TPSLIMIT:-}" >>"$FAKE_REPO/calls"
[[ $RESTIC_PASSWORD == made-up-password && $RCLONE_CONFIG_PASS == made-up-rclone ]] ||
	{ echo "Fatal: wrong password" >&2; exit 1; }
[[ $1 == -o && $2 == rclone.timeout=* ]] && shift 2
if [[ $1 == unlock ]]; then
	for lock in "$locks"/*; do
		[[ -e $lock ]] || continue
		kill -0 "${lock##*/}" 2>/dev/null || rm -f -- "$lock"
	done
	echo "successfully removed locks"
	exit 0
fi
for lock in "$locks"/*; do
	[[ -e $lock ]] || continue
	echo "unable to create lock in backend: repository is already locked by PID ${lock##*/} on test by root (UID 0, GID 0)" >&2
	echo "the \`unlock\` command can be used to remove stale locks" >&2
	exit 11
done
touch "$locks/$$"
case $1 in
	dump) printf 'PGDMP'; head -c 1048576 /dev/zero || exit $? ;;
	snapshots) echo '[{"short_id":"abcd1234"}]' ;;
esac
rm -f -- "$locks/$$"
FAKE
chmod +x "$work/bin/restic"

# in_ops SCRIPT: runs SCRIPT with set -euo pipefail and the restic library
# loaded, as the ops scripts do; stdout to $work/out, stderr to $work/err.
# SIGPIPE is set back to its default, as for a script run by hand with sudo,
# which is how the restore test ran on 2026-11-03. GitHub Actions starts jobs
# with SIGPIPE ignored (so do systemd units, IgnoreSIGPIPE=yes), and then a
# writer cut off by an early reader fails with "Broken pipe" instead of being
# killed. bash cannot reset a signal ignored when it started, so env does it.
in_ops() {
	PATH="$work/bin:$PATH" FAKE_REPO="$work/repo" env --default-signal=PIPE bash -c '
		set -euo pipefail
		cd "$1"
		. ops/lib/errors.sh
		. ops/lib/restic.sh
		restic_password=made-up-password
		rclone_config_pass=made-up-rclone
		eval "$2"
	' _ "$repo" "$1" >"$work/out" 2>"$work/err"
}
locks() { find "$work/repo/locks" -type f | wc -l; }
# The restore test's command before the fix: pg_restore --list reads only
# the archive's table of contents, as head -c 5 does here.
early_reader='expected=$(run_restic dump abcd1234 /dixie-detail.dump | head -c 5 | wc -c); echo "reached the end"'

echo "test-restic: an early reader cuts restic off (the 2026-11-03 incident)"
if in_ops "$early_reader"; then fail "the script carried on"; else pass "the script stops"; fi
[[ ! -s $work/out && ! -s $work/err ]] && pass "and says nothing, without report_failures" || fail "it printed: $(cat "$work/out" "$work/err")"
[[ $(locks) == 1 ]] && pass "restic, cut off, leaves its lock in the repository" || fail "$(locks) locks left"

echo "test-restic: a locked repository names the unlock command"
if in_ops 'run_restic forget --prune'; then fail "forget succeeded on a locked repository"; else pass "forget fails"; fi
grep -q "repository is already locked" "$work/err" && pass "restic's own error is shown" || fail "restic's error is missing"
grep -q "sudo /srv/dixie-detail/ops/restic.sh unlock" "$work/err" && pass "the unlock command is named" ||
	fail "no unlock command in: $(cat "$work/err")"
grep -q "The backup repository is locked" "$work/err" && pass "the troubleshooting entry is named" || fail "no troubleshooting pointer"
in_ops 'run_restic unlock' && [[ $(locks) == 0 ]] && pass "unlock removes the stale lock" || fail "$(locks) locks after unlock"
in_ops 'run_restic snapshots' && pass "restic works again after unlock" || fail "still failing: $(cat "$work/err")"
grep -q "unlock" "$work/err" && fail "the hint showed without a lock" || pass "no hint when the repository is not locked"

echo "test-restic: report_failures says what failed"
if in_ops "report_failures restore-test; $early_reader"; then fail "the script carried on"; else pass "the script stops"; fi
grep -q "restore-test: FAIL: .* line [0-9]*: expected=.* exited with status 141; 141 means a command was cut off" "$work/err" &&
	pass "it names the command, the line and the SIGPIPE status" || fail "it printed: $(cat "$work/err")"
in_ops 'run_restic unlock' >/dev/null
rc=0
in_ops 'report_failures test; f() { false; echo "not reached"; }; f' || rc=$?
[[ $rc == 1 && $(grep -c "FAIL" "$work/err") == 1 ]] && grep -q "line [0-9]*: false exited with status 1" "$work/err" &&
	pass "a failure inside a function is reported once, and the exit status kept" || fail "status $rc, printed: $(cat "$work/err")"
in_ops 'report_failures test; x=$(false; true); if false; then :; fi; false || true; echo done'
[[ $(cat "$work/out") == "done" && ! -s $work/err ]] && pass "handled failures and failures inside \$(...) that do not end the script are not reported" ||
	fail "printed: $(cat "$work/err")"
in_ops 'report_failures test; a=1 | false | true' || true
grep -q "pipeline parts: 0 1 0" "$work/err" && pass "a pipeline shows each part's status" || fail "printed: $(cat "$work/err")"

echo "test-restic: restic_dump writes to a file, so nothing cuts it off"
PATH="$work/bin:$PATH" FAKE_REPO="$work/repo" env --default-signal=PIPE bash -c '
	set -euo pipefail
	cd "$1"
	. ops/lib/errors.sh
	. ops/lib/restic.sh
	restic_password=made-up-password rclone_config_pass=made-up-rclone
	restic_dump abcd1234 /dixie-detail.dump "$2/dump"
	head -c 5 "$2/dump" >/dev/null
' _ "$repo" "$work" && pass "the dump and an early reader of the file both succeed" || fail "restic_dump failed"
[[ $(stat -c %s "$work/dump" 2>/dev/null) == 1048581 ]] && pass "the whole dump is written" || fail "the dump is $(stat -c %s "$work/dump" 2>/dev/null) bytes"
[[ $(locks) == 0 ]] && pass "no lock is left" || fail "$(locks) locks left"

echo "test-restic: no ops script pipes restic's output"
piped=$(grep -nE '^[^#]*run_restic' "$repo"/ops/*.sh "$repo"/ops/lib/*.sh | sed 's/||//g' | grep -E 'run_restic[^#]*\|' || true)
[[ -z $piped ]] && pass "run_restic's output never goes into a pipe" || fail "piped: $piped"
bare=$(grep -nE '^[^#]*(^|[^_[:alnum:]])restic ' "$repo"/ops/*.sh | grep -vE 'run_restic|restic\.sh|echo' || true)
[[ -z $bare ]] && pass "every script runs restic through run_restic" || fail "restic run directly: $bare"
grep -q 'restic_dump' "$repo/ops/restore-test.sh" && pass "restore-test.sh downloads with restic_dump" || fail "restore-test.sh does not use restic_dump"
for script in backup.sh restore-test.sh gosu-test.sh; do
	grep -q 'report_failures' "$repo/ops/$script" && pass "$script reports failures" || fail "$script does not call report_failures"
done

echo "test-restic: every restic call gets the 5-minute rclone timeout and the Drive call limit"
rm -f "$work/repo/calls"
in_ops 'run_restic snapshots >/dev/null; restic_dump latest /dixie-detail.dump /dev/null'
[[ $(wc -l <"$work/repo/calls") == 2 ]] && ! grep -v '^-o rclone.timeout=5m .*|tps=5$' "$work/repo/calls" &&
	pass "run_restic and restic_dump pass -o rclone.timeout=5m and RCLONE_TPSLIMIT=5" || fail "calls: $(cat "$work/repo/calls")"

echo "test-restic: restic_time_limit stops a restic that hangs, with SIGINT so it can remove its lock"
mkdir -p "$work/hang"
cat >"$work/hang/restic" <<'FAKE'
#!/usr/bin/env bash
trap 'echo "made-up restic: interrupted, lock removed" >&2; exit 130' INT
for _ in $(seq 300); do sleep 0.1; done
FAKE
chmod +x "$work/hang/restic"
rc=0
PATH="$work/hang:$PATH" bash -c '
	. "$1/ops/lib/restic.sh"
	restic_password=made-up-password rclone_config_pass=made-up-rclone restic_time_limit=1s
	run_restic backup
' _ "$repo" 2>"$work/err" || rc=$?
[[ $rc == 124 ]] && grep -q "interrupted, lock removed" "$work/err" && pass "stopped after 1 second with SIGINT, exit status 124" ||
	fail "status $rc, printed: $(cat "$work/err")"

# ops/backup.sh against fakes. The fake restic fails the first
# FAKE_FAIL_BACKUP backup calls and the first FAKE_FAIL_FORGET forget calls
# with exit status FAKE_RC, logging each call and how many bytes of stdin a
# backup got. The fake sleep only records how long it was asked to wait.
mkdir -p "$work/fake"
cat >"$work/fake/restic" <<'FAKE'
#!/usr/bin/env bash
printf '%s|tps=%s\n' "$*" "${RCLONE_TPSLIMIT:-}" >>"$FAKE_DIR/restic-calls"
[[ $RESTIC_PASSWORD == made-up-password && $RCLONE_CONFIG_PASS == made-up-rclone ]] ||
	{ echo "Fatal: wrong password or no key found" >&2; exit 12; }
[[ $1 == -o ]] && shift 2
command=$1
[[ $1 == backup && " $* " == *" --tag photos "* ]] && command=photos
echo "$command" >>"$FAKE_DIR/commands"
n=$(grep -cx "$command" "$FAKE_DIR/commands")
case $command in
	backup) echo "$(wc -c)" >>"$FAKE_DIR/stdin-bytes"; fails=${FAKE_FAIL_BACKUP:-0} ;;
	forget) fails=${FAKE_FAIL_FORGET:-0} ;;
	photos) printf '%s\n' "$*" >>"$FAKE_DIR/photo-calls"; fails=${FAKE_FAIL_PHOTOS:-0} ;;
esac
if ((n <= fails)); then
	echo "Fatal: unable to open repository at rclone:gdrive:made-up: error talking HTTP to rclone: made-up error $1 $n" >&2
	exit "${FAKE_RC:-1}"
fi
echo "made-up $1 output"
FAKE
cat >"$work/fake/bws" <<'FAKE'
#!/usr/bin/env bash
echo '[{"key":"RESTIC_PASSWORD","value":"made-up-password"},{"key":"RCLONE_CONFIG_PASS","value":"made-up-rclone"},{"key":"HEALTHCHECKS_BACKUP_URL","value":"https://hc.example.invalid/ping/made-up"}]'
FAKE
cat >"$work/fake/docker" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >>"$FAKE_DIR/docker-calls"
case "$*" in
	*pg_dump*) printf 'PGDMP made-up dump\n' ;;
	*pg_restore*) cat >/dev/null ;;
esac
FAKE
cat >"$work/fake/curl" <<'FAKE'
#!/usr/bin/env bash
url=$(sed -n 's/^url = "\(.*\)"$/\1/p')
echo "$url" >>"$FAKE_DIR/pings"
for arg; do [[ $arg != @* ]] || cp -- "${arg#@}" "$FAKE_DIR/ping-body"; done
FAKE
printf '#!/bin/sh\necho "$1" >>"$FAKE_DIR/sleeps"\n' >"$work/fake/sleep"
printf '#!/bin/sh\necho "$*" >>"$FAKE_DIR/rsync-calls"\n' >"$work/fake/rsync"
printf '#!/bin/sh\nexit 0\n' >"$work/fake/mountpoint"
chmod +x "$work/fake"/*
printf 'made-up-token' >"$work/bws-token"

# run_backup [VAR=VALUE...]: runs ops/backup.sh with the fakes and a fresh
# state; its output goes to $work/b/out. Prints its exit status.
run_backup() {
	rm -rf "$work/b"
	mkdir -p "$work/b/run" "$work/b/creds" "$work/b/photos"
	cp "$work/bws-token" "$work/b/creds/bws-token"
	local rc=0
	env "$@" PATH="$work/fake:$PATH" FAKE_DIR="$work/b" RUNTIME_DIRECTORY="$work/b/run" \
		CREDENTIALS_DIRECTORY="$work/b/creds" BWS_SERVER_URL=https://vault.example.invalid \
		BWS_PROJECT_ID=made-up-project BACKUP_DIR="$work/b/backups" \
		RESTIC_REPOSITORY=rclone:gdrive:made-up POSTGRES_DB=dixie POSTGRES_USER=dixie QUOTE_PHOTO_HOST_DIR="$work/b/photos" \
		"$repo/ops/backup.sh" >"$work/b/out" 2>&1 || rc=$?
	echo "$rc"
}
count() { grep -cx "$1" "$work/b/commands" 2>/dev/null || true; }
sleeps() { tr '\n' ' ' 2>/dev/null <"$work/b/sleeps" | sed 's/ $//'; }
failed_ping() { grep -q '/fail$' "$work/b/pings"; }

echo "test-restic: backup.sh retries an upload that fails once"
rc=$(run_backup FAKE_FAIL_BACKUP=1)
[[ $rc == 0 ]] && pass "the run ends as a success" || fail "exit status $rc: $(tail -5 "$work/b/out")"
[[ $(count backup) == 2 && $(count forget) == 1 ]] && pass "two upload attempts, one forget" || fail "$(count backup) uploads, $(count forget) forgets"
[[ $(sleeps) == 300 ]] && pass "it waited 5 minutes before the second attempt" || fail "waits: $(sleeps)"
[[ $(sort -u "$work/b/stdin-bytes") == 19 ]] && pass "both attempts got the whole dump" || fail "bytes: $(cat "$work/b/stdin-bytes")"
[[ $(grep -c pg_dump "$work/b/docker-calls") == 1 ]] && pass "the database was dumped once" || fail "dumped $(grep -c pg_dump "$work/b/docker-calls") times"
grep -q "upload, attempt 1 of 3, failed with exit status 1" "$work/b/out" && grep -q "made-up error backup 1" "$work/b/out" &&
	grep -q "upload succeeded on attempt 2 of 3" "$work/b/out" && pass "each attempt and its error are logged" || fail "log: $(cat "$work/b/out")"
! failed_ping && [[ $(tail -1 "$work/b/pings") == https://hc.example.invalid/ping/made-up ]] && pass "the success ping is sent" ||
	fail "pings: $(cat "$work/b/pings")"
! grep -v '^-o rclone.timeout=5m .*|tps=5$' "$work/b/restic-calls" && pass "every restic call in the backup gets the timeout and the call limit" ||
	fail "calls: $(cat "$work/b/restic-calls")"

echo "test-restic: backup.sh gives up after three failed uploads"
rc=$(run_backup FAKE_FAIL_BACKUP=9)
[[ $rc != 0 ]] && pass "the run fails" || fail "the run succeeded"
[[ $(count backup) == 3 && $(count forget) == 0 ]] && pass "three upload attempts, no forget" || fail "$(count backup) uploads, $(count forget) forgets"
[[ $(sleeps) == "300 900" ]] && pass "it waited 5, then 15 minutes" || fail "waits: $(sleeps)"
[[ $(grep -c pg_dump "$work/b/docker-calls") == 1 ]] && pass "the database dump is not retried" || fail "dumped $(grep -c pg_dump "$work/b/docker-calls") times"
failed_ping && pass "the failure ping is sent" || fail "pings: $(cat "$work/b/pings")"
for n in 1 2 3; do
	grep -q "upload, attempt $n of 3" "$work/b/ping-body" && grep -q "made-up error backup $n" "$work/b/ping-body" ||
		fail "attempt $n is missing from the ping's log"
done
grep -q "upload failed 3 times; giving up" "$work/b/ping-body" && pass "the failure ping carries every attempt's error" || fail "no summary in the ping's log"
[[ $(stat -c %s "$work/b/ping-body") -le 10000 ]] && pass "and stays within 10,000 bytes" || fail "ping body is $(stat -c %s "$work/b/ping-body") bytes"

echo "test-restic: backup.sh retries forget/prune as its own step"
rc=$(run_backup FAKE_FAIL_FORGET=2)
[[ $rc == 0 && $(count backup) == 1 && $(count forget) == 3 && $(sleeps) == "300 900" ]] &&
	pass "one upload, three forget attempts, then success" || fail "status $rc, $(count backup) uploads, $(count forget) forgets, waits $(sleeps)"

echo "test-restic: backup.sh copies the photo folder to the RAID and sends it once, tagged photos"
rc=$(run_backup)
[[ $rc == 0 && $(count photos) == 1 ]] && pass "one photo upload" || fail "status $rc, $(count photos) photo uploads"
grep -q -- "--tag photos $work/b/photos" "$work/b/photo-calls" && pass "the photo folder is sent tagged photos" || fail "photo calls: $(cat "$work/b/photo-calls" 2>/dev/null)"
grep -q -- "--tag nightly --tag photos --group-by host,tags" "$work/b/restic-calls" && pass "forget keeps each tag's own 14 daily / 12 monthly" || fail "calls: $(cat "$work/b/restic-calls")"
grep -q -- "-a --delete -- $work/b/photos/ $work/b/backups/quote-photos/" "$work/b/rsync-calls" && pass "the folder is mirrored to the RAID" || fail "rsync: $(cat "$work/b/rsync-calls" 2>/dev/null)"
[[ $(tail -1 "$work/b/commands") == photos ]] && pass "the photos go last, after forget/prune" || fail "order: $(tr '\n' ' ' <"$work/b/commands")"

echo "test-restic: a failed photo upload is not retried and fails the run"
rc=$(run_backup FAKE_FAIL_PHOTOS=9)
[[ $rc != 0 && $(count photos) == 1 && $(count backup) == 1 && $(count forget) == 1 && -z $(sleeps) ]] && failed_ping &&
	grep -q "photo upload failed 1 times; giving up" "$work/b/ping-body" &&
	pass "one attempt, no wait, failure ping" || fail "status $rc, $(count photos) photo uploads, waits $(sleeps)"

echo "test-restic: backup.sh does not retry what waiting cannot fix"
for code in 12 10; do
	rc=$(run_backup FAKE_FAIL_BACKUP=9 FAKE_RC=$code)
	[[ $rc == "$code" && $(count backup) == 1 && -z $(sleeps) ]] && failed_ping && grep -q "upload is not retried" "$work/b/ping-body" &&
		pass "exit $code: one attempt, no wait, failure ping" || fail "exit $code: status $rc, $(count backup) uploads, waits $(sleeps)"
done

((failures == 0)) || { echo "test-restic: $failures failure(s)" >&2; exit 1; }
echo "test-restic: PASS"
