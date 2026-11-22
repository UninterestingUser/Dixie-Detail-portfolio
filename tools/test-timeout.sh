#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Checks that the timeout command run_restic uses (gnu_timeout in
# ops/lib/restic.sh) behaves as the ops scripts expect. On Ubuntu 26.04 the
# plain `timeout` is uutils' 0.10.0, which, given --signal=INT with
# --kill-after, sends SIGKILL at once, so a restic cut off at its time limit
# can't remove its lock; gnu_timeout picks GNU's `gnutimeout` there.
#
# Checks, with made-up children and no restic:
#   1. time running out: exit status 124;
#   2. the backup's own form (--signal=INT --kill-after): the child gets
#      SIGINT, can clean up and exit, and timeout exits 124;
#   3. a child that ignores SIGINT is killed after --kill-after: status 137,
#      not before the grace period;
#   4. a child that exits by itself passes its own status through (7 and 0).
# Also says whether the plain `timeout` on this machine would pass check 2,
# for information only.
#
# Needs bash and coreutils. Takes about 10 seconds. Run by tools/run-tests.sh,
# and on the server, as any user:  /srv/dixie-detail/tools/test-timeout.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0

pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

# shellcheck source=../ops/lib/restic.sh
. "$repo/ops/lib/restic.sh"
picked=$(gnu_timeout) || { echo "test-timeout: FAIL: no GNU coreutils timeout to use" >&2; exit 1; }
echo "test-timeout: run_restic uses $(command -v "$picked"): $("$picked" --version | head -1)"

# A child like restic: on SIGINT it says so and exits by itself.
cat >"$work/polite" <<'CHILD'
#!/usr/bin/env bash
trap 'echo "child: got SIGINT, cleaned up"; exit 130' INT
for _ in $(seq 100); do sleep 0.1; done
echo "child: never interrupted"
CHILD
# A child that ignores SIGINT.
cat >"$work/stubborn" <<'CHILD'
#!/usr/bin/env bash
trap '' INT
for _ in $(seq 100); do sleep 0.1; done
CHILD
chmod +x "$work/polite" "$work/stubborn"

# run TIMEOUT ARGS...: sets rc, out and seconds (whole seconds taken).
run() {
	local start=$SECONDS
	rc=0
	out=$("$@" 2>&1) || rc=$?
	seconds=$((SECONDS - start))
}

run "$picked" 1 sleep 5
[[ $rc == 124 ]] && pass "1. time running out exits 124" || fail "1. time running out exited $rc"

run "$picked" --signal=INT --kill-after=5 1 "$work/polite"
[[ $rc == 124 && $out == *"got SIGINT, cleaned up"* ]] && pass "2. --signal=INT --kill-after: the child gets SIGINT, cleans up, and timeout exits 124" ||
	fail "2. --signal=INT --kill-after: exit $rc, child said: ${out:-nothing}"

run "$picked" --signal=INT --kill-after=2 1 "$work/stubborn"
[[ $rc == 137 && $seconds -ge 3 ]] && pass "3. a child ignoring SIGINT is killed after the --kill-after grace: exit 137 after ${seconds}s" ||
	fail "3. a child ignoring SIGINT: exit $rc after ${seconds}s (expected 137 after 3s)"

run "$picked" --signal=INT --kill-after=5 5 sh -c 'exit 7'
first=$rc
run "$picked" --signal=INT --kill-after=5 5 true
[[ $first == 7 && $rc == 0 ]] && pass "4. a child that exits by itself keeps its status (7 and 0)" ||
	fail "4. a child that exits by itself: exit $first and $rc (expected 7 and 0)"

if [[ $picked != timeout ]] && command -v timeout >/dev/null; then
	run timeout --signal=INT --kill-after=5 1 "$work/polite"
	if [[ $rc == 124 && $out == *"got SIGINT"* ]]; then
		echo "  note: the plain timeout ($(timeout --version | head -1)) would pass check 2 too"
	else
		echo "  note: the plain timeout ($(timeout --version | head -1)) fails check 2 (exit $rc), which is why run_restic doesn't use it"
	fi
fi

if ((failures)); then
	echo "test-timeout: $failures FAILED" >&2
	exit 1
fi
echo "test-timeout: PASS"
