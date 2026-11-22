#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file. The
# scripts in single quotes run in a child bash, so they must not expand here.
# shellcheck disable=SC2015,SC2016
# Tests ops/lib/restic.sh and ops/lib/errors.sh against a fake restic that,
# like the real one, locks the repository while it works and leaves the lock
# behind when it is killed. Reproduces the 2026-11-03 incident: a reader that
# stopped early cut restic off mid-dump, the restore test quit without a
# message, and the stale lock failed every backup until `restic unlock`.
# Also checks how run_restic hands restic its repository, password and keys
# (decision 0127). ops/backup.sh's own runs are tested in tools/test-backup.sh.
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
printf '%s|repo=%s|user=%s|rest=%s|aws=%s:%s\n' "$*" "${RESTIC_REPOSITORY:-}" "${RESTIC_REST_USERNAME:-}" \
	"${RESTIC_REST_PASSWORD:-}" "${AWS_ACCESS_KEY_ID:-}" "${AWS_SECRET_ACCESS_KEY:-}" >>"$FAKE_REPO/calls"
[[ $RESTIC_PASSWORD == made-up-password ]] || { echo "Fatal: wrong password" >&2; exit 1; }
[[ $1 == --cacert ]] && shift 2
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
		B2_REPOSITORY=s3:https://s3.us-west-004.backblazeb2.com/made-up-bucket/restic
		restic_use b2
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
grep -q "sudo /srv/dixie-detail/ops/restic.sh --repo b2 unlock" "$work/err" && pass "the unlock command is named" ||
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
	restic_password=made-up-password restic_repository=made-up-repo
	restic_dump abcd1234 /dixie-detail.dump "$2/dump"
	head -c 5 "$2/dump" >/dev/null
' _ "$repo" "$work" && pass "the dump and an early reader of the file both succeed" || fail "restic_dump failed"
[[ $(stat -c %s "$work/dump" 2>/dev/null) == 1048581 ]] && pass "the whole dump is written" || fail "the dump is $(stat -c %s "$work/dump" 2>/dev/null) bytes"
[[ $(locks) == 0 ]] && pass "no lock is left" || fail "$(locks) locks left"

echo "test-restic: no ops script pipes restic's output"
piped=$(grep -nE '^[^#]*run_restic' "$repo"/ops/*.sh "$repo"/ops/*/*.sh | sed 's/||//g' | grep -E 'run_restic[^#]*\|' || true)
[[ -z $piped ]] && pass "run_restic's output never goes into a pipe" || fail "piped: $piped"
bare=$(grep -nE '^[^#]*(^|[^_[:alnum:]])restic ' "$repo"/ops/*.sh "$repo"/ops/*/*.sh | grep -vE 'run_restic|restic\.sh|echo|for tool in' || true)
[[ -z $bare ]] && pass "every script runs restic through run_restic" || fail "restic run directly: $bare"
grep -q 'restic_dump' "$repo/ops/restore-test.sh" && pass "restore-test.sh downloads with restic_dump" || fail "restore-test.sh does not use restic_dump"
for script in backup.sh restore-test.sh restore.sh offsite-prune.sh gosu-test.sh backup-host/weekly.sh; do
	grep -q 'report_failures' "$repo/ops/$script" && pass "$script reports failures" || fail "$script does not call report_failures"
done

echo "test-restic: run_restic hands each repository its password and keys in the environment only"
rm -f "$work/repo/calls"
in_ops 'b2_key_id=made-up-key-id b2_application_key=made-up-app-key; run_restic snapshots >/dev/null; restic_dump latest /dixie-detail.dump /dev/null'
[[ $(wc -l <"$work/repo/calls") == 2 ]] && ! grep -v '|repo=s3:https://s3.us-west-004.backblazeb2.com/made-up-bucket/restic|.*|aws=made-up-key-id:made-up-app-key$' "$work/repo/calls" &&
	pass "B2: the S3 repository and the key, as AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY" || fail "calls: $(cat "$work/repo/calls")"
rm -f "$work/repo/calls"
in_ops 'BACKUP_HOST_ADDRESS=192.0.2.20 BACKUP_REST_CACERT=/etc/made-up.pem; restic_use backup-server; rest_password=made-up-rest; run_restic snapshots >/dev/null'
grep -q '^--cacert /etc/made-up.pem snapshots|repo=rest:https://192.0.2.20:8443/dixie-detail/|user=dixie-detail|rest=made-up-rest|' "$work/repo/calls" &&
	pass "the backup server: rest-server's address, the pinned certificate, the user and its password" || fail "calls: $(cat "$work/repo/calls")"
! grep -qE 'made-up-(password|rest|app-key)' <(cut -d'|' -f1 "$work/repo/calls") &&
	pass "no password or key is ever on restic's command line" || fail "calls: $(cat "$work/repo/calls")"
in_ops 'restic_use nowhere' && fail "an unknown repository was accepted" || pass "an unknown repository is refused"
in_ops 'unset B2_REPOSITORY; restic_use b2' && fail "a missing B2_REPOSITORY was accepted" || grep -q "set B2_REPOSITORY in .env" "$work/err" &&
	pass "a missing setting is named" || fail "printed: $(cat "$work/err")"

echo "test-restic: restic_init_labeled leaves one key, labeled restic/restic"
cat >"$work/bin/restic-keys" <<'FAKE'
#!/usr/bin/env bash
# A fake restic with a key list: init makes one key labeled with a real
# host and user, key add another, key remove drops one.
state="$FAKE_REPO/keys.json"
[[ $1 == --cacert ]] && shift 2
case $1 in
	cat) [[ -e $FAKE_REPO/initialized ]] ;;
	init) touch "$FAKE_REPO/initialized"; echo '[{"id":"aaaa","userName":"owner","hostName":"real-host"}]' >"$state" ;;
	key)
		case $2 in
			list) cat "$state" ;;
			add) [[ $(cat) == made-up-password ]] || exit 1
				jq --arg u "$6" --arg h "$4" '. + [{id:"bbbb",userName:$u,hostName:$h}]' "$state" >"$state.new" && mv "$state.new" "$state" ;;
			remove) jq --arg id "${@: -1}" 'map(select(.id != $id))' "$state" >"$state.new" && mv "$state.new" "$state" ;;
		esac ;;
esac
FAKE
chmod +x "$work/bin/restic-keys"
rm -f "$work/repo/initialized"
mkdir -p "$work/keysbin" && ln -sf "$work/bin/restic-keys" "$work/keysbin/restic"
PATH="$work/keysbin:$PATH" FAKE_REPO="$work/repo" bash -c '
	set -euo pipefail
	cd "$1"; . ops/lib/restic.sh
	restic_password=made-up-password B2_REPOSITORY=s3:https://s3.us-west-004.backblazeb2.com/b/r
	restic_use b2
	restic_init_labeled
' _ "$repo" >"$work/out" 2>"$work/err" && jq -e 'length == 1 and .[0].userName == "restic" and .[0].hostName == "restic"' "$work/repo/keys.json" >/dev/null &&
	pass "the first key, with the real host and user, is replaced" || fail "keys: $(cat "$work/repo/keys.json" 2>/dev/null) $(cat "$work/err")"

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
	restic_password=made-up-password restic_repository=made-up-repo restic_time_limit=1s
	run_restic backup
' _ "$repo" 2>"$work/err" || rc=$?
[[ $rc == 124 ]] && grep -q "interrupted, lock removed" "$work/err" && pass "stopped after 1 second with SIGINT, exit status 124" ||
	fail "status $rc, printed: $(cat "$work/err")"

echo "test-restic: run_restic uses a GNU timeout, never uutils' (Ubuntu 26.04)"
# A fake uutils timeout, which kills at once, as uutils 0.10.0 does when
# given --signal=INT with --kill-after, and a real GNU one as gnutimeout.
real_gnu=$(bash -c '. "$1/ops/lib/restic.sh"; command -v "$(gnu_timeout)"' _ "$repo")
mkdir -p "$work/uutils" "$work/both"
cat >"$work/uutils/timeout" <<'FAKE'
#!/usr/bin/env bash
[[ $1 == --version ]] && { echo "timeout (uutils coreutils) 0.10.0"; exit 0; }
echo "fake uutils timeout ran" >>"$FAKE_LOG"
exit 137
FAKE
chmod +x "$work/uutils/timeout"
cp "$work/uutils/timeout" "$work/both/timeout"
ln -s "$real_gnu" "$work/both/gnutimeout"
rc=0
FAKE_LOG="$work/uutils.log" PATH="$work/uutils:$work/hang:/usr/bin:/bin" bash -c '
	. "$1/ops/lib/restic.sh"
	# Hide a real gnutimeout on this machine.
	command() { [[ $1 == -v && $2 == gnutimeout ]] && return 1; builtin command "$@"; }
	restic_password=made-up-password restic_repository=made-up-repo restic_time_limit=1s
	run_restic backup
' _ "$repo" 2>"$work/err" || rc=$?
[[ $rc != 0 && ! -e $work/uutils.log ]] && grep -q "no GNU coreutils timeout found" "$work/err" &&
	pass "with only a uutils timeout, run_restic refuses and starts nothing" || fail "status $rc, printed: $(cat "$work/err")"
rc=0
FAKE_LOG="$work/uutils.log" PATH="$work/uutils:$work/hang:/usr/bin:/bin" bash -c '
	. "$1/ops/lib/restic.sh"
	command() { [[ $1 == -v && $2 == gnutimeout ]] && return 1; builtin command "$@"; }
	restic_password=made-up-password restic_repository=made-up-repo
	run_restic snapshots
' _ "$repo" 2>"$work/err" || rc=$?
[[ $rc != 0 ]] && grep -q "/usr/bin/gnutimeout is missing. Install it with: sudo apt install gnu-coreutils" "$work/err" &&
	pass "without a time limit too, a missing GNU timeout stops run_restic with a clear error" || fail "status $rc, printed: $(cat "$work/err")"
rc=0
FAKE_LOG="$work/both.log" PATH="$work/both:$work/hang:$PATH" bash -c '
	. "$1/ops/lib/restic.sh"
	restic_password=made-up-password restic_repository=made-up-repo restic_time_limit=1s
	run_restic backup
' _ "$repo" 2>"$work/err" || rc=$?
[[ $rc == 124 && ! -e $work/both.log ]] && grep -q "interrupted, lock removed" "$work/err" &&
	pass "with uutils as timeout and GNU as gnutimeout, gnutimeout runs: SIGINT, exit status 124" || fail "status $rc, printed: $(cat "$work/err")"

((failures == 0)) || { echo "test-restic: $failures failure(s)" >&2; exit 1; }
echo "test-restic: PASS"
