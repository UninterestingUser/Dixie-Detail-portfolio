#!/usr/bin/env bash
# Run the app's tests the same way on the workstation and on GitHub Actions:
# pytest in a container built from the production Python image, against a
# throwaway PostgreSQL database that lives in memory and is removed afterwards.
# Then check that the production image cannot load the development settings.
# First, the ops scripts' Bitwarden helper is tested with a fake bws
# (tools/test-bws.sh, which needs jq).
#
# Usage, from anywhere in the repository:  tools/run-tests.sh [pytest arguments]
# Uses Podman, or Docker where Podman is not installed. CONTAINER_ENGINE=docker
# forces one.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
engine=${CONTAINER_ENGINE:-$(command -v podman || command -v docker || true)}
[[ -n $engine ]] || { echo "run-tests: install Podman: sudo dnf install podman" >&2; exit 1; }

# The same PostgreSQL image as the db service in compose.yaml.
postgres_image=docker.io/library/$(grep -m1 -oE 'postgres:[^[:space:]]+' "$repo/compose.yaml")
db=dixie-test-db-$$

cleanup() { "$engine" rm -f "$db" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "run-tests: testing the Bitwarden helper (ops/lib/bws.sh)"
"$repo/tools/test-bws.sh" >/dev/null || { "$repo/tools/test-bws.sh"; exit 1; }

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
