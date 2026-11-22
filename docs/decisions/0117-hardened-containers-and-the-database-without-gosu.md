---
id: 117
title: "Every container is hardened, and the database runs as the postgres user so gosu is never called"
summary: "compose.yaml adds no-new-privileges, drops every capability (Caddy keeps one), uses read-only roots and process limits, and starts PostgreSQL as uid 999, so a kernel that hangs gosu no longer stops it."
date: 2026-11-21
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [compose.yaml, docs/decisions/0088-kernels-tested-before-default.md, docs/operations/updating-the-kernel.md, ops/gosu-test.sh, ops/restore-test.sh, docs/architecture/server-and-stack.md]
---

# 0117: Every container is hardened, and the database runs as the postgres user so gosu is never called

**Status:** accepted · **Date:** 2026-11-21 · **Area:** infrastructure

## Context

A review (finding L6) noted that the containers ran with Docker's defaults: the usual set of Linux capabilities, the right to gain privileges through setuid binaries, writable root file systems except the app's, and no process limit. Separately (finding H4), the database started as root and switched to the postgres user with `gosu`, which hung on kernel 7.0.0-42 under Docker's AppArmor profile (decision 0088). The review asked to test starting it as `user: "999:999"`, which the PostgreSQL image supports and which skips gosu entirely.

## Decision

- **Every service** has `no-new-privileges`, `cap_drop: [ALL]` and a `pids_limit` well above what it uses (db 256, app 128, calendar worker 64, Caddy 128, cloudflared 128).
- **Capabilities.** None is needed: the database, app, calendar worker and cloudflared run as users without root's powers, and Caddy binds only ports 8000 and 8080. Caddy alone gets `NET_BIND_SERVICE` back, because the image's binary is marked with it as a file capability and the kernel refuses to start a binary whose file capability has been dropped ("exec /usr/bin/caddy: operation not permitted", found in testing).
- **Read-only root file systems** for every service. The writable places are the volumes, plus in-memory folders: `/run/postgresql` (the socket and lock file) and `/tmp` for the database, `/tmp` for the app and the calendar worker, and Caddy's `/data` and `/config` (with admin and automatic HTTPS off it keeps nothing worth saving).
- **The database runs as `999:999`,** the image's postgres user, from the start. The entrypoint then never calls gosu. The data folder on the existing volume already belongs to that user, because the root entrypoint gave it to postgres when the volume was made. The stack's secret file for it was already owned by uid 999 (`ops/stack-start.sh`).
- **The restore test** starts its throwaway PostgreSQL the same way, and feeds the dump to `pg_restore` on its standard input instead of mounting the folder, so the root-only folder in `/dev/shm` stays root's.
- **The gosu test** now first starts a throwaway PostgreSQL the way the stack starts it, and that decides the result. It still tries `gosu postgres true`, but only reports a hang.

## How it was tested

On the workstation, with Podman and made-up values: a volume made by the previous `compose.yaml` (root entrypoint and gosu), then the hardened stack started on it. The database started as postgres with its earlier rows, the app migrated and passed its healthcheck, both Caddy entrances answered (`/health`, the sign-in redirect, the public API, a 404 for anything else), quote photos could be written and the app's code could not, the calendar worker started, one-off `compose run` commands worked, and every process showed no effective capabilities (Caddy only `NET_BIND_SERVICE`) and no-new-privileges set. cloudflared, run the same way with a made-up token and no network, started and stopped only where it would dial out. A dump taken as the nightly backup takes it restored with the restore test's steps, every table present. The server check after the deploy is in [updating-the-kernel.md](../operations/updating-the-kernel.md#the-stack-no-longer-depends-on-gosu).

## Alternatives considered

- **Keep the database starting as root, depending on the kernel test alone.** It works while each new kernel is tested, but one untested reboot into a bad kernel stops the database.
- **AppArmor unconfined for the database.** Turns a protection off to work around a bug; ruled out in decision 0088.
- **Run Caddy as a non-root user.** The file capability check applies to any user, so it needs `NET_BIND_SERVICE` either way, and running as root without capabilities gives it no more than that.

## Consequences

A kernel that hangs gosu no longer stops the stack, so the kernel test (decision 0088) protects against other faults rather than this one. A new service added to `compose.yaml` follows the same pattern. Anything that later needs a writable folder outside a volume needs a tmpfs entry, and the container's log says which path was read-only. Podman, on the workstation, refuses `uid=` on a tmpfs, so the database's tmpfs uses `mode=1777` instead, which works under both.
