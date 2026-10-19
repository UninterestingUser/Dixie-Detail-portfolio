#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests ops/lib/bws.sh against a fake bws that answers "429 Too Many Requests"
# a set number of times. Needs bash and jq; no Bitwarden and no real secret.
# Run by tools/run-tests.sh, or on its own:  tools/test-bws.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0

pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

# A fake bws. FAKE_429 says how many calls are refused first; FAKE_ERROR
# makes every call fail with another error instead. Each call is counted.
mkdir -p "$work/bin" "$work/creds"
cat >"$work/bin/bws" <<'FAKE'
#!/usr/bin/env bash
count=$(( $(cat "$FAKE_DIR/calls" 2>/dev/null || echo 0) + 1 ))
echo "$count" >"$FAKE_DIR/calls"
[[ $BWS_ACCESS_TOKEN == made-up-token ]] || { echo "Error: no token" >&2; exit 1; }
if [[ -n ${FAKE_ERROR:-} ]]; then echo "Error: $FAKE_ERROR" >&2; exit 1; fi
if ((count <= ${FAKE_429:-0})); then
	echo "Error: Received error message from server: [429 Too Many Requests] Slow down! Too many requests. Try again in 1m." >&2
	exit 1
fi
echo '[{"key":"FIRST_SECRET","value":"made-up-one"},{"key":"SECOND_SECRET","value":"made-up-two"}]'
FAKE
chmod +x "$work/bin/bws"
printf 'made-up-token' >"$work/creds/bws-token"

# run_case NAME FAKE_429 [FAKE_ERROR]: loads the secrets in a fresh shell and
# prints what it read; stderr goes to $work/stderr.
run_case() {
	rm -f "$work/calls"
	PATH="$work/bin:$PATH" FAKE_DIR="$work" FAKE_429="$2" FAKE_ERROR="${3:-}" \
		CREDENTIALS_DIRECTORY="$work/creds" BWS_SERVER_URL=https://vault.example.invalid BWS_RETRY_SECONDS=0 \
		bash -c '
			set -euo pipefail
			. "$1/ops/lib/bws.sh"
			bws_load made-up-project
			bws_load made-up-project
			printf "%s|%s|%s" "$(bws_get FIRST_SECRET)" "$(bws_get SECOND_SECRET)" "$(bws_get_optional MISSING_SECRET)"
		' _ "$repo" 2>"$work/stderr"
}
calls() { cat "$work/calls"; }
retries() { grep -c "retry .* of 3 in 0 seconds" "$work/stderr" || true; }

echo "test-bws: one call per run"
out=$(run_case one 0)
[[ $out == "made-up-one|made-up-two|" ]] && pass "both secrets read, a missing optional one is empty" || fail "read $out"
[[ $(calls) == 1 ]] && pass "one bws call for two secrets and two loads" || fail "$(calls) calls"

echo "test-bws: a 429 is retried"
out=$(run_case retry 2)
[[ $out == "made-up-one|made-up-two|" ]] && pass "succeeds after two 429s" || fail "read $out"
[[ $(calls) == 3 && $(retries) == 2 ]] && pass "three calls, each retry logged" || fail "$(calls) calls, $(retries) retries logged"

echo "test-bws: up to three retries"
if run_case give-up 4 >/dev/null; then fail "succeeded after four 429s"; else pass "fails after four 429s"; fi
[[ $(calls) == 4 && $(retries) == 3 ]] && pass "four calls, three retries" || fail "$(calls) calls, $(retries) retries logged"
grep -q "429 Too Many Requests" "$work/stderr" && pass "the last error is shown" || fail "the error was not shown"

echo "test-bws: other errors are not retried"
if run_case other 0 "Unauthorized" >/dev/null; then fail "succeeded on an error"; else pass "fails at once"; fi
[[ $(calls) == 1 && $(retries) == 0 ]] && pass "one call, no retry" || fail "$(calls) calls, $(retries) retries"

echo "test-bws: every ops script fetches through bws_load"
direct=$(grep -nE 'bws_project_secrets|bws_value|bws_optional_value|bws secret' "$repo"/ops/*.sh "$repo"/ops/lib/restic.sh || true)
[[ -z $direct ]] && pass "no script calls bws or reads secrets around the helper" || fail "direct use: $direct"
for script in backup.sh restore-test.sh public-health.sh stack-start.sh deploy.sh restic.sh; do
	if grep -qE 'bws_load|restic_load_secrets' "$repo/ops/$script"; then pass "$script uses bws_load"; else fail "$script does not use bws_load"; fi
done

((failures == 0)) || { echo "test-bws: $failures failure(s)" >&2; exit 1; }
echo "test-bws: PASS"
