#!/usr/bin/env bash
# Writes the part of the monitor account's status report that needs root
# (decision 0128): each container's state and health, and the NVMe drive's
# health. Run every 5 minutes by dixie-monitor-snapshot.timer. The file is
# replaced in one rename and is readable by everyone; it holds no secret.
set -uo pipefail

OUT=${MONITOR_SNAPSHOT:-/var/lib/dixie-monitor/status}
NVME=${MONITOR_NVME:-/dev/nvme0}
cd "${DIXIE_DIR:-/srv/dixie-detail}" || exit 1
install -d -m 0755 "$(dirname "$OUT")"
tmp=$(mktemp "$OUT.XXXXXX")
{
	echo "Written: $(TZ=America/New_York date '+%F %H:%M %Z')"
	echo "Containers (service, state, health, status):"
	docker compose ps --all --format '  {{.Service}}	{{.State}}	{{.Health}}	{{.Status}}' 2>&1 || echo "  docker compose ps failed"
	echo "NVMe ($NVME):"
	smartctl -H -A "$NVME" 2>&1 |
		grep -E 'overall-health|Critical Warning|Temperature:|Available Spare:|Percentage Used|Media and Data Integrity Errors|Unsafe Shutdowns|Power On Hours' |
		sed 's/^/  /' || echo "  smartctl gave no health lines (is smartmontools installed?)"
} >"$tmp"
chmod 0644 "$tmp"
mv -f -- "$tmp" "$OUT"
