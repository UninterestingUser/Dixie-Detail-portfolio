#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests site/workers/offline-replay/deploy.sh (decision 0116) with a fake
# wrangler: the namespace id is looked up by its title, the deploy uses a copy
# of wrangler.toml holding it, the copy is removed afterwards, wrangler.toml
# itself is never changed, and a missing, doubled or unreadable namespace
# stops the deploy with a message. Needs bash and node; no network.
# Run by tools/run-tests.sh, or on its own:  tools/test-worker-deploy.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0

pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

command -v node >/dev/null || { echo "test-worker-deploy: node is not installed" >&2; exit 1; }

worker="$work/worker"
mkdir -p "$worker"
cp "$repo/site/workers/offline-replay/deploy.sh" "$repo/site/workers/offline-replay/wrangler.toml" "$worker/"
original=$(cat "$worker/wrangler.toml")

# The fake wrangler: `kv namespace list` prints $FAKE_LIST; `deploy` records
# its arguments and the config it was given.
cat >"$work/wrangler" <<'EOF'
#!/usr/bin/env bash
if [[ $1 == kv && $2 == namespace && $3 == list ]]; then
	[[ -n ${FAKE_LIST_FAILS:-} ]] && { echo "Not logged in" >&2; exit 1; }
	printf '%s\n' "$FAKE_LIST"
	exit 0
fi
if [[ $1 == deploy ]]; then
	echo "$@" >"$FAKE_OUT/args"
	shift
	while (($#)); do
		[[ $1 == --config ]] && { cp "$2" "$FAKE_OUT/config"; echo "$2" >"$FAKE_OUT/config-path"; }
		shift
	done
	exit 0
fi
echo "fake wrangler: unexpected $*" >&2
exit 9
EOF
chmod +x "$work/wrangler"
export WRANGLER="$work/wrangler" FAKE_OUT="$work/out"

id=0123456789abcdef0123456789abcdef
other=fedcba9876543210fedcba9876543210
listing="[{\"id\": \"$other\", \"title\": \"dixie-offline-replay-OFFLINE_REQUESTS\"}, {\"id\": \"$id\", \"title\": \"OFFLINE_REQUESTS\"}]"

run() { rm -rf "$FAKE_OUT"; mkdir -p "$FAKE_OUT"; "$worker/deploy.sh" "$@" >"$work/stdout" 2>"$work/stderr"; }

echo "test-worker-deploy: a deploy looks the id up by title"
FAKE_LIST=$listing run --dry-run && pass "the deploy succeeds" || fail "the deploy failed: $(cat "$work/stderr")"
grep -q "id = \"$id\"" "$FAKE_OUT/config" 2>/dev/null && pass "the deploy config holds the namespace titled OFFLINE_REQUESTS" || fail "the deploy config lacks the id"
! grep -q "$other" "$FAKE_OUT/config" 2>/dev/null && pass "a namespace with a longer title is not taken" || fail "the wrong namespace was taken"
grep -q -- "--dry-run" "$FAKE_OUT/args" 2>/dev/null && pass "extra arguments reach wrangler deploy" || fail "--dry-run was not passed on"
config_path=$(cat "$FAKE_OUT/config-path" 2>/dev/null || true)
[[ $(dirname "$config_path") == "$worker" ]] && pass "the copy sits beside wrangler.toml" || fail "the copy was at $config_path"
[[ -n $config_path && ! -e $config_path ]] && pass "the copy is removed afterwards" || fail "the copy was left behind"
[[ $(cat "$worker/wrangler.toml") == "$original" ]] && pass "wrangler.toml is unchanged" || fail "wrangler.toml was changed"
diff <(grep -v '^id = ' "$FAKE_OUT/config") <(grep -v '^id = ' "$worker/wrangler.toml") >/dev/null &&
	pass "only the id differs from wrangler.toml" || fail "the copy differs from wrangler.toml beyond the id"

echo "test-worker-deploy: --id prints the id only"
FAKE_LIST=$listing run --id && [[ $(cat "$work/stdout") == "$id" ]] && pass "--id prints the id" || fail "--id printed $(cat "$work/stdout")"
[[ ! -e $FAKE_OUT/args ]] && pass "--id deploys nothing" || fail "--id deployed"

echo "test-worker-deploy: each problem stops the deploy"
expect_stop() { # label pattern
	if run; then fail "$1: the deploy went ahead"; return; fi
	grep -q "$2" "$work/stderr" && pass "$1" || fail "$1: said $(cat "$work/stderr")"
	[[ ! -e $FAKE_OUT/args ]] || fail "$1: wrangler deploy ran"
}
FAKE_LIST="[{\"id\": \"$other\", \"title\": \"OTHER\"}]" expect_stop "no namespace with the title" "no KV namespace titled OFFLINE_REQUESTS"
FAKE_LIST="[{\"id\": \"$id\", \"title\": \"OFFLINE_REQUESTS\"}, {\"id\": \"$other\", \"title\": \"OFFLINE_REQUESTS\"}]" expect_stop "two namespaces with the title" "more than one"
FAKE_LIST="not json" expect_stop "an unreadable list" "couldn't read"
FAKE_LIST="[{\"id\": \"x\\\"; rm -rf\", \"title\": \"OFFLINE_REQUESTS\"}]" expect_stop "an id that isn't a namespace id" "couldn't read"
FAKE_LIST_FAILS=1 FAKE_LIST=$listing expect_stop "wrangler not signed in" "login"
sed -i "s/SET_TO_THE_OFFLINE_REQUESTS_NAMESPACE_ID/$other/" "$worker/wrangler.toml"
FAKE_LIST=$listing expect_stop "an id written into wrangler.toml" "no longer holds the placeholder"
[[ -z $(find "$worker" -name '.wrangler-deploy-*') ]] && pass "no copy is left after a stop" || fail "a copy was left after a stop"

if ((failures)); then
	echo "test-worker-deploy: $failures FAILED" >&2
	exit 1
fi
echo "test-worker-deploy: PASS"
