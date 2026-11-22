#!/usr/bin/env bash
# The gosu test: checks that the running kernel can start the database
# container. Run on the server as root after booting a new kernel, before
# making it the GRUB default (docs/operations/updating-the-kernel.md):
#
#   sudo /srv/dixie-detail/ops/gosu-test.sh
#
# The PostgreSQL image's entrypoint switches from root to the postgres user
# with gosu. On Ubuntu kernel 7.0.0-42, under Docker's default AppArmor
# profile, gosu hangs there and logs no AppArmor denial, so the database
# never starts (the 2026-11-03 incident). Kernel 7.0.0-38 works. Since
# decision 0117 the stack's database and the restore test start as the
# postgres user, so they never call gosu; the gosu check stays, as a report.
#
# Uses the stack's own PostgreSQL image, in throwaway containers with no
# network, so it does not touch the running stack or the database:
#   1. a throwaway PostgreSQL, started as the stack starts it (the postgres
#      user, read-only, no capabilities), must answer within 60 seconds;
#   2. `gosu postgres true` is tried for 30 seconds, and a hang is reported
#      (with whether AppArmor is involved) but doesn't fail the test.
# Ends with "gosu-test: PASS" or exits 1.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
container="dixie-gosu-test-$$"

[[ $EUID -eq 0 ]] || { echo "gosu-test: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
# shellcheck source=lib/errors.sh
. ops/lib/errors.sh
report_failures gosu-test

image=$(grep -m1 -oE 'postgres:[^[:space:]]+' compose.yaml)
remove() { timeout 30 docker rm -f "$container" >/dev/null 2>&1 || true; }
trap remove EXIT

# gosu_runs [docker run options]: true if `gosu postgres true` finishes in 30 s.
gosu_runs() {
	local rc=0
	timeout 30 docker run --rm --name "$container" --network none "$@" \
		--entrypoint gosu "$image" postgres true || rc=$?
	remove
	return "$rc"
}

echo "Kernel $(uname -r), image $image"

echo "1. a throwaway PostgreSQL starts the way the stack starts it"
docker run --detach --rm --name "$container" --network none --user 999:999 --read-only \
	--tmpfs /var/lib/postgresql:mode=1777 --tmpfs /run/postgresql:mode=1777 --tmpfs /tmp \
	--cap-drop ALL --security-opt no-new-privileges:true \
	-e POSTGRES_HOST_AUTH_METHOD=trust "$image" >/dev/null
# TCP only answers once initialization is over and the real server is up.
ready() { timeout 10 docker exec "$container" pg_isready -q -h 127.0.0.1; }
for _ in $(seq 60); do
	ready && break
	sleep 1
done
if ! ready; then
	echo "gosu-test: FAIL: PostgreSQL did not start within 60 seconds. Its log:" >&2
	timeout 10 docker logs --tail 20 "$container" >&2 || true
	echo "   Keep the previous kernel as the GRUB default; see docs/operations/updating-the-kernel.md." >&2
	exit 1
fi
remove
echo "   ok"

# Nothing in the stack calls gosu any more (decision 0117); a hang here is
# worth knowing about, not a reason to keep the old kernel.
echo "2. gosu postgres true (a report only)"
if gosu_runs; then
	echo "   ok"
else
	echo "   gosu did not finish within 30 seconds under Docker's default AppArmor profile." >&2
	if gosu_runs --security-opt apparmor=unconfined; then
		echo "   Without AppArmor confinement it finishes: the AppArmor hang of kernel 7.0.0-42." >&2
	else
		echo "   It also fails without AppArmor confinement." >&2
	fi
	echo "   The stack doesn't use gosu, so this doesn't fail the test. Note it in docs/operations/troubleshooting.md." >&2
fi

echo "gosu-test: PASS"
