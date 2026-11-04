#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file. The
# scripts in single quotes run in a child bash, so they must not expand here.
# shellcheck disable=SC2015,SC2016
# Tests ops/lib/restic.sh and ops/lib/errors.sh against a fake restic that,
# like the real one, locks the repository while it works and leaves the lock
# behind when it is killed. Reproduces the 2026-11-03 incident: a reader that
# stopped early cut restic off mid-dump, the restore test quit without a
# message, and the stale lock failed every backup until `restic unlock`.
# Needs bash and coreutils; no restic, no repository and no real secret.
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
[[ $RESTIC_PASSWORD == made-up-password && $RCLONE_CONFIG_PASS == made-up-rclone ]] ||
	{ echo "Fatal: wrong password" >&2; exit 1; }
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
in_ops() {
	PATH="$work/bin:$PATH" FAKE_REPO="$work/repo" bash -c '
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
PATH="$work/bin:$PATH" FAKE_REPO="$work/repo" bash -c '
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

((failures == 0)) || { echo "test-restic: $failures failure(s)" >&2; exit 1; }
echo "test-restic: PASS"
