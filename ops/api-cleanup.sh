#!/usr/bin/env bash
# Nightly public API cleanup. Run by dixie-api-cleanup.service
# (dixie-api-cleanup.timer, every night at 2:20 AM).
#
# Runs `clean_public_api` in a one-off app container, which mounts the photo
# folder like the app does (compose.yaml): it deletes quote request photos
# never attached to a sent request after a day, a closed request's photos
# QUOTE_REQUEST_PHOTO_DAYS after it closed, stray files in the photo folder,
# unused places and old rate counts (docs/reference/public-api.md, decision
# 0099). It needs no secret of its own and sends no ping: a failure shows in
# `systemctl list-timers --failed` and the journal.
set -euo pipefail

cd "$(dirname "$0")/.."
exec docker compose run --rm --no-deps -T app python manage.py clean_public_api
