#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests the deploy and the stack's start (decision 0125) against fakes of
# bws, docker, systemctl, systemd-creds, install and chown, in a throwaway
# copy of ops/:
#   - a deploy whose secret fetch fails, or whose build fails, leaves the
#     running stack as it was: no compose up or down, no systemctl restart or
#     stop of the stack, the old secret files untouched, and it says so;
#   - a deploy that works swaps the secret files in, recreates only what
#     changed (compose up, never down, never --force-recreate), and creates
#     the health check's credential when it's missing;
#   - with the stack stopped, the deploy starts it with systemctl;
#   - stack-start.sh exits non-zero when Bitwarden can't be reached (not
#     only on a 429) and when a container doesn't come up healthy, so
#     dixie-stack.service's Restart=on-failure tries again;
#   - dixie-stack.service restarts itself every minute, without a limit;
#   - the public health check reads its own credential, never Bitwarden.
# Needs bash, jq and coreutils; no Docker, no root, no network.
# Run by tools/run-tests.sh, or on its own:  tools/test-deploy.sh
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0
pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

mkdir -p "$work/bin" "$work/repo" "$work/units" "$work/run/dixie-stack" "$work/stage"
cp -r "$repo/ops" "$work/repo/"
printf 'BWS_PROJECT_ID=made-up-project\nBWS_SERVER_URL=https://vault.example\n' >"$work/repo/.env"

# A fake bws: the project's secrets as JSON, or an error (FAKE_BWS_ERROR).
cat >"$work/bin/bws" <<'FAKE'
#!/usr/bin/env bash
echo "bws $*" >>"$FAKE_LOG"
if [[ -n ${FAKE_BWS_ERROR:-} ]]; then echo "Error: $FAKE_BWS_ERROR" >&2; exit 1; fi
jq -n --arg env "${FAKE_DOT_ENV-}" '[{key:"POSTGRES_PASSWORD",value:"made-up-pg"},{key:"DJANGO_SECRET_KEY",value:"made-up-django"},
	{key:"CLOUDFLARE_TUNNEL_TOKEN",value:"made-up-tunnel"},{key:"HEALTHCHECKS_PUBLIC_URL",value:"https://hc.example/made-up"}]
	+ (if $env == "" then [] else [{key:"DOT_ENV",value:$env}] end)'
FAKE
# A fake docker: logs every call; `compose build` fails with FAKE_BUILD_FAILS,
# `compose up` with FAKE_UP_FAILS.
cat >"$work/bin/docker" <<'FAKE'
#!/usr/bin/env bash
echo "docker $*" >>"$FAKE_LOG"
[[ $1 == compose && $2 == build && -n ${FAKE_BUILD_FAILS:-} ]] && { echo "build failed" >&2; exit 1; }
[[ $1 == compose && $2 == up && -n ${FAKE_UP_FAILS:-} ]] && { echo "container dixie-app-1 is unhealthy" >&2; exit 1; }
exit 0
FAKE
# A fake systemctl: logs every call; is-active says FAKE_ACTIVE.
cat >"$work/bin/systemctl" <<'FAKE'
#!/usr/bin/env bash
echo "systemctl $*" >>"$FAKE_LOG"
case $1 in
	is-active) [[ $* == *dixie-stack* ]] && { [[ -n ${FAKE_ACTIVE:-} ]]; exit; }; exit 0 ;;
	is-enabled) exit 0 ;;
esac
exit 0
FAKE
# A fake systemd-creds: decrypt prints a made-up Bitwarden token; encrypt
# writes what it was given, so the test can read it.
cat >"$work/bin/systemd-creds" <<'FAKE'
#!/usr/bin/env bash
echo "systemd-creds $*" >>"$FAKE_LOG"
[[ $1 == decrypt ]] && { echo made-up-token; exit 0; }
cat >"${@: -1}"
FAKE
# Fake install and chown: log, and copy unit files where told.
cat >"$work/bin/install" <<'FAKE'
#!/usr/bin/env bash
echo "install $*" >>"$FAKE_LOG"
[[ $1 == -m && -f $3 ]] && cp "$3" "$4"
exit 0
FAKE
printf '#!/usr/bin/env bash\nexit 0\n' >"$work/bin/chown"
chmod +x "$work/bin/"*
export FAKE_LOG="$work/log" PATH="$work/bin:$PATH"
export SYSTEMD_UNIT_DIR="$work/units" STACK_STAGE_PARENT="$work/stage" STACK_RUN_DIR="$work/run/dixie-stack" HEALTH_CRED="$work/health.cred"

# deploy: runs deploy_apply as deploy.sh does after the pull. Sets rc.
deploy() {
	: >"$FAKE_LOG"
	rc=0
	(cd "$work/repo" && bash -c '
		set -euo pipefail
		. ops/lib/bws.sh; . ops/lib/settings.sh; . ops/lib/stack.sh; . ops/lib/deploy.sh
		deploy_apply
	') </dev/null >"$work/out" 2>&1 || rc=$?
}
# A running stack's secret files, to see whether a deploy touches them.
running_stack() {
	rm -rf "$STACK_RUN_DIR/secrets"
	mkdir -p "$STACK_RUN_DIR/secrets/app"
	echo old >"$STACK_RUN_DIR/secrets/app/django_secret_key"
}
untouched() { # what a failed deploy must not have done
	! grep -qE "^docker compose (up|down)|^systemctl (restart|stop|start) dixie-stack" "$FAKE_LOG" &&
		[[ $(cat "$STACK_RUN_DIR/secrets/app/django_secret_key") == old ]] && [[ -z $(ls -A "$STACK_STAGE_PARENT") ]]
}

echo "test-deploy: a deploy that can't fetch the secrets leaves the running stack as it was"
running_stack
FAKE_ACTIVE=1 FAKE_BWS_ERROR="error sending request: dns error" deploy
[[ $rc != 0 ]] && pass "the deploy fails" || fail "the deploy succeeded"
untouched && pass "no container recreated, stopped or restarted; the old secret files kept" || fail "it touched the stack: $(cat "$FAKE_LOG")"
! grep -q "^docker compose build" "$FAKE_LOG" && pass "it stopped before building" || fail "it built anyway"
grep -q "couldn't fetch the secrets from Bitwarden. The running stack was left as it was" "$work/out" && pass "it says the stack was left as it was" || fail "said: $(cat "$work/out")"

echo "test-deploy: a deploy whose build fails leaves the running stack as it was"
running_stack
FAKE_ACTIVE=1 FAKE_BUILD_FAILS=1 deploy
[[ $rc != 0 ]] && untouched && grep -q "the image build failed. The running stack was left as it was" "$work/out" &&
	pass "fails, touches nothing, and says so" || fail "rc $rc, log: $(cat "$FAKE_LOG"), said: $(cat "$work/out")"
! grep -q "^install -m 0644" "$FAKE_LOG" && pass "no unit was installed before the build passed" || fail "units were installed"

echo "test-deploy: a deploy that works recreates only what changed"
running_stack
rm -f "$HEALTH_CRED"
FAKE_ACTIVE=1 deploy
[[ $rc == 0 ]] && pass "the deploy succeeds" || fail "rc $rc: $(cat "$work/out")"
grep -qx "docker compose up --detach --remove-orphans --wait --wait-timeout 600" "$FAKE_LOG" && pass "docker compose up, waiting for healthy containers" || fail "calls: $(grep '^docker' "$FAKE_LOG")"
! grep -qE "^docker compose down|force-recreate|^systemctl (restart|stop) dixie-stack" "$FAKE_LOG" && pass "never down, never --force-recreate, never a stack restart" || fail "calls: $(cat "$FAKE_LOG")"
[[ $(grep -n "^docker compose build" "$FAKE_LOG" | cut -d: -f1) -lt $(grep -n "^docker compose up" "$FAKE_LOG" | cut -d: -f1) ]] && pass "built before anything was recreated" || fail "order: $(cat "$FAKE_LOG")"
[[ $(cat "$STACK_RUN_DIR/secrets/app/django_secret_key") == made-up-django && ! -e $STACK_RUN_DIR/secrets.old ]] && pass "the new secret files are in place" || fail "secrets: $(ls -R "$STACK_RUN_DIR")"
[[ -z $(ls -A "$STACK_STAGE_PARENT") ]] && pass "the staging folder is gone" || fail "left: $(ls "$STACK_STAGE_PARENT")"
[[ $(cat "$HEALTH_CRED") == https://hc.example/made-up ]] && grep -q "systemd-creds encrypt --with-key=auto --name=healthchecks-public-url" "$FAKE_LOG" &&
	pass "the missing health check credential was created" || fail "credential: $(cat "$HEALTH_CRED" 2>/dev/null)"
grep -q "^systemctl restart dixie-tunnel-firewall.service" "$FAKE_LOG" && [[ -f $SYSTEMD_UNIT_DIR/dixie-tunnel-firewall.service ]] &&
	pass "the tunnel firewall's unit is installed and applied" || fail "firewall: $(grep firewall "$FAKE_LOG")"
FAKE_ACTIVE=1 deploy
! grep -q "systemd-creds encrypt" "$FAKE_LOG" && pass "an existing credential is left alone" || fail "it rewrote the credential"
running_stack
FAKE_ACTIVE=1 FAKE_UP_FAILS=1 deploy
[[ $rc != 0 ]] && grep -q "didn't all come up running and healthy" "$work/out" && pass "an unhealthy container fails the deploy, with a message" || fail "rc $rc, said: $(cat "$work/out")"

echo "test-deploy: every systemd-creds encrypt works on a host without a TPM (decision 0130)"
# The public copy has no docs/operations, so its absence is no failure.
encrypts=$(grep -rnE "systemd-creds encrypt +-" "$repo/ops" "$repo/docs/operations" 2>/dev/null || true)
[[ $(wc -l <<<"$encrypts") -ge 3 ]] && ! grep -v -- "--with-key=auto " <<<"$encrypts" &&
	pass "each uses --with-key=auto" || fail "without --with-key=auto: $encrypts"

echo "test-deploy: the deploy compares .env with the DOT_ENV secret"
running_stack
FAKE_ACTIVE=1 FAKE_DOT_ENV=$(cat "$work/repo/.env") deploy
[[ $rc == 0 ]] && grep -q ".env matches the DOT_ENV secret" "$work/out" && pass "the same: it says so" || fail "rc $rc, said: $(cat "$work/out")"
running_stack
FAKE_ACTIVE=1 FAKE_DOT_ENV=$'BWS_PROJECT_ID=made-up-project\nBWS_SERVER_URL=https://other.example\nOLD_SETTING=made-up-value' deploy
[[ $rc == 0 ]] && grep -q "WARNING: .env differs from the DOT_ENV secret in Bitwarden, in: BWS_SERVER_URL OLD_SETTING\." "$work/out" &&
	pass "different: a warning naming the settings, and the deploy goes on" || fail "rc $rc, said: $(cat "$work/out")"
! grep -qE "other\.example|made-up-value|vault\.example" "$work/out" && pass "no setting's value is printed" || fail "said: $(cat "$work/out")"
running_stack
FAKE_ACTIVE=1 deploy
[[ $rc == 0 ]] && grep -q "there's no DOT_ENV secret in Bitwarden" "$work/out" && pass "missing: a warning" || fail "rc $rc, said: $(cat "$work/out")"

echo "test-deploy: with the stack stopped, the deploy starts it"
rm -rf "$STACK_RUN_DIR/secrets"
deploy
grep -qx "systemctl start dixie-stack.service" "$FAKE_LOG" && ! grep -q "^docker compose up" "$FAKE_LOG" && pass "systemctl start dixie-stack.service" || fail "calls: $(cat "$FAKE_LOG")"

echo "test-deploy: stack-start.sh fails on anything, so the unit tries again"
start() {
	: >"$FAKE_LOG"
	rc=0
	(cd "$work/repo" && CREDENTIALS_DIRECTORY="$work" RUNTIME_DIRECTORY="$work/run/dixie-stack" BWS_PROJECT_ID=made-up-project BWS_SERVER_URL=https://vault.example \
		BWS_RETRY_SECONDS=0 ops/stack-start.sh) </dev/null >"$work/out" 2>&1 || rc=$?
}
echo made-up-token >"$work/bws-token"
FAKE_BWS_ERROR="error sending request: connection refused" start
[[ $rc != 0 ]] && ! grep -q "^docker" "$FAKE_LOG" && grep -q "couldn't fetch the secrets from Bitwarden" "$work/out" &&
	pass "Bitwarden unreachable (not a 429): exits non-zero before starting anything" || fail "rc $rc, said: $(cat "$work/out")"
FAKE_UP_FAILS=1 start
[[ $rc != 0 ]] && grep -q "didn't all come up running and healthy" "$work/out" && pass "a container that isn't healthy: exits non-zero" || fail "rc $rc, said: $(cat "$work/out")"
start
[[ $rc == 0 ]] && grep -qx "docker compose up --detach --remove-orphans --wait --wait-timeout 600 --force-recreate" "$FAKE_LOG" &&
	pass "a good start recreates every container and waits for them" || fail "rc $rc, calls: $(cat "$FAKE_LOG")"

echo "test-deploy: the tunnel hold keeps the connector stopped (decision 0128)"
export TUNNEL_HOLD="$work/hold-tunnel"
touch "$TUNNEL_HOLD"
start
[[ $rc == 0 ]] && grep -qx "docker compose up --detach --remove-orphans --wait --wait-timeout 600 --scale cloudflared=0 --scale calendar-worker=0 --force-recreate" "$FAKE_LOG" &&
	grep -q "the tunnel is held" "$work/out" && pass "a start while held runs everything but cloudflared, and says so" || fail "rc $rc, calls: $(cat "$FAKE_LOG")"
running_stack
FAKE_ACTIVE=1 deploy
grep -qx "docker compose up --detach --remove-orphans --wait --wait-timeout 600 --scale cloudflared=0 --scale calendar-worker=0" "$FAKE_LOG" &&
	pass "a deploy while held keeps cloudflared and the calendar worker at 0" || fail "calls: $(cat "$FAKE_LOG")"
hold() { : >"$FAKE_LOG"; rc=0; printf '%s\n' "${2:-}" >"$work/tty"; (cd "$work/repo" && DIXIE_EUID=0 DIXIE_DIR="$work/repo" DIXIE_TTY="$work/tty" FAKE_ACTIVE=1 ops/tunnel-hold.sh "$1") >"$work/out" 2>&1 || rc=$?; }
hold off no
[[ $rc != 0 && -e $TUNNEL_HOLD ]] && ! grep -q "^docker compose up" "$FAKE_LOG" && pass "off without confirming the other connector is stopped changes nothing" || fail "rc $rc: $(cat "$work/out")"
hold off yes
[[ $rc == 0 && ! -e $TUNNEL_HOLD ]] && grep -qx "docker compose up --detach --remove-orphans --wait --wait-timeout 600" "$FAKE_LOG" &&
	pass "off, confirmed, starts the connector" || fail "rc $rc, calls: $(cat "$FAKE_LOG")"
hold on
[[ $rc == 0 && -e $TUNNEL_HOLD ]] && grep -qx "docker compose stop cloudflared calendar-worker" "$FAKE_LOG" && pass "on stops a running connector and calendar worker" || fail "rc $rc, calls: $(cat "$FAKE_LOG")"
rm -f "$TUNNEL_HOLD"

echo "test-deploy: the units"
unit="$repo/ops/dixie-stack.service"
grep -qx "Restart=on-failure" "$unit" && grep -qx "RestartSec=60" "$unit" && grep -qx "StartLimitIntervalSec=0" "$unit" &&
	pass "dixie-stack.service tries again every minute, without a limit" || fail "dixie-stack.service lacks its restart lines"
health="$repo/ops/dixie-public-health.service"
grep -q "^LoadCredentialEncrypted=healthchecks-public-url:" "$health" && ! grep -q "bws-token" "$health" && ! grep -q "bws_" "$repo/ops/public-health.sh" &&
	pass "the public health check reads its own credential and never calls Bitwarden" || fail "the public health check still uses Bitwarden"

if ((failures)); then
	echo "test-deploy: $failures FAILED" >&2
	exit 1
fi
echo "test-deploy: PASS"
