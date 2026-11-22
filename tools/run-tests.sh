#!/usr/bin/env bash
# Run the app's tests the same way on the workstation and on GitHub Actions:
# pytest in a container built from the production Python image, against a
# throwaway PostgreSQL database that lives in memory and is removed afterwards.
# Then check that the production image cannot load the development settings.
# First, the ops scripts' Bitwarden helper is tested with a fake bws
# (tools/test-bws.sh, which needs jq), and their restic and failure-reporting
# helpers and the backup's retries with a fake restic (tools/test-restic.sh),
# and the portfolio publisher against throwaway repositories
# (tools/test-portfolio.sh, which needs git filter-repo and python3), and the
# offline Worker's deploy script with a fake wrangler (tools/test-worker-deploy.sh,
# which needs node), the deploy and the stack's start with fakes
# (tools/test-deploy.sh), the tunnel firewall's rules in a network
# namespace of its own (tools/test-tunnel-firewall.sh), the hourly and
# nightly backups (tools/test-backup.sh), the backup host's scripts and the
# restore (tools/test-backup-host.sh, which needs openssl), and the
# production host's firewall, UPS, monitor account and requests-only switch
# (tools/test-host-setup.sh), all with fakes.
#
# Usage, from anywhere in the repository:  tools/run-tests.sh [pytest arguments]
#   tools/run-tests.sh --ops-only   runs only the ops-script tests, with no
#   container engine (the Tests workflow runs them on Ubuntu 26.04, the
#   server's release).
# Uses Podman, or Docker where Podman is not installed. CONTAINER_ENGINE=docker
# forces one.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
ops_only=false
[[ ${1:-} == --ops-only ]] && { ops_only=true; shift; }
engine=${CONTAINER_ENGINE:-$(command -v podman || command -v docker || true)}
$ops_only || [[ -n $engine ]] || { echo "run-tests: install Podman: sudo dnf install podman" >&2; exit 1; }

# The same PostgreSQL image as the db service in compose.yaml.
postgres_image=docker.io/library/$(grep -m1 -oE 'postgres:[^[:space:]]+' "$repo/compose.yaml")
db=dixie-test-db-$$

cleanup() { "$engine" rm -f "$db" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "run-tests: testing the Bitwarden helper (ops/lib/bws.sh)"
"$repo/tools/test-bws.sh" >/dev/null || { "$repo/tools/test-bws.sh"; exit 1; }
echo "run-tests: testing the timeout run_restic uses (tools/test-timeout.sh)"
"$repo/tools/test-timeout.sh" >/dev/null || { "$repo/tools/test-timeout.sh"; exit 1; }
echo "run-tests: testing the restic and failure helpers (ops/lib/restic.sh, ops/lib/errors.sh)"
"$repo/tools/test-restic.sh" >/dev/null || { "$repo/tools/test-restic.sh"; exit 1; }
echo "run-tests: testing the hourly and nightly backups (ops/backup.sh)"
"$repo/tools/test-backup.sh" >/dev/null || { "$repo/tools/test-backup.sh"; exit 1; }
echo "run-tests: testing the backup host's scripts and the restore (ops/backup-host/, ops/restore.sh)"
"$repo/tools/test-backup-host.sh" >/dev/null || { "$repo/tools/test-backup-host.sh"; exit 1; }
echo "run-tests: testing the production host's setup scripts (firewall, UPS, monitor account, site mode)"
"$repo/tools/test-host-setup.sh" >/dev/null || { "$repo/tools/test-host-setup.sh"; exit 1; }
echo "run-tests: testing the deploy and the stack's start (ops/lib/deploy.sh, ops/stack-start.sh)"
"$repo/tools/test-deploy.sh" >/dev/null || { "$repo/tools/test-deploy.sh"; exit 1; }
echo "run-tests: testing the tunnel firewall (ops/tunnel-firewall.sh)"
"$repo/tools/test-tunnel-firewall.sh" >/dev/null || { "$repo/tools/test-tunnel-firewall.sh"; exit 1; }
echo "run-tests: testing the portfolio publisher (tools/publish-portfolio.sh)"
"$repo/tools/test-portfolio.sh" >/dev/null || { "$repo/tools/test-portfolio.sh"; exit 1; }

echo "run-tests: testing the offline Worker's deploy script (site/workers/offline-replay/deploy.sh)"
"$repo/tools/test-worker-deploy.sh" >/dev/null || { "$repo/tools/test-worker-deploy.sh"; exit 1; }

if $ops_only; then
	echo "run-tests: PASS (ops scripts only)"
	exit 0
fi

# The test image must use the production image's base (Dependabot updates
# both in one pull request, decision 0118).
base() { grep -m1 -oE '^FROM [^[:space:]]+' "$1" | sed -E 's|^FROM (docker\.io/library/)?||'; }
[[ $(base "$repo/app/Dockerfile") == "$(base "$repo/app/Dockerfile.test")" ]] ||
	{ echo "run-tests: FAIL: app/Dockerfile and app/Dockerfile.test use different base images" >&2; exit 1; }

echo "run-tests: building the test image"
"$engine" build -q -t dixie-app-test:local -f "$repo/app/Dockerfile.test" "$repo/app" >/dev/null

echo "run-tests: starting $postgres_image"
# Made-up values, matching app/dixie/settings_dev.py. No port is published:
# the tests join this container's network instead.
"$engine" run -d --name "$db" --tmpfs /var/lib/postgresql \
	-e POSTGRES_DB=dixie -e POSTGRES_USER=dixie -e POSTGRES_PASSWORD=dixie-dev-password \
	"$postgres_image" -c fsync=off -c synchronous_commit=off -c full_page_writes=off >/dev/null

# Over TCP, so the temporary server the image runs during first setup (which
# listens on a socket only) does not count as ready.
ready() { "$engine" exec "$db" pg_isready -q -h 127.0.0.1 -U dixie -d dixie; }
for _ in $(seq 60); do ready && break; sleep 0.5; done
ready || { "$engine" logs "$db" >&2; echo "run-tests: PostgreSQL did not start" >&2; exit 1; }

echo "run-tests: running pytest"
"$engine" run --rm --network "container:$db" --security-opt label=disable \
	-v "$repo/app:/srv/app:ro" -v "$repo/data:/srv/data:ro" dixie-app-test:local python -m pytest "$@"

echo "run-tests: checking the production image leaves out the development settings"
"$engine" build -q -t dixie-app:test-check "$repo/app" >/dev/null
"$engine" run --rm dixie-app:test-check python -c \
	'import importlib.util, sys; sys.exit(importlib.util.find_spec("dixie.settings_dev") is not None)' ||
	{ echo "run-tests: FAIL: the production image contains dixie/settings_dev.py" >&2; exit 1; }

echo "run-tests: PASS"
