---
id: 123
title: "The public API is its own service, and photos are decoded in a sandboxed worker"
summary: "A public service from the same image serves only /health and /api/public/, the app serves the control app, and a photo worker with no network, secrets or database decodes each upload."
date: 2026-11-22
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [compose.yaml, caddy/Caddyfile, app/core/middleware.py, app/photoworker/worker.py, app/publicapi/photos.py, docs/architecture/network-and-access.md, docs/architecture/server-and-stack.md, docs/decisions/0099-quote-requests-with-photos.md, docs/decisions/0120-photo-uploads-reach-only-four-decoders.md]
---

# 0123: The public API is its own service, and photos are decoded in a sandboxed worker

**Status:** accepted · **Date:** 2026-11-22 · **Area:** infrastructure

## Context

A review (finding M3) noted that one `app` service served both doors. A rush of website traffic, or one slow request, used the same three gunicorn workers the owner needs for the control app. And every uploaded photo, from anyone on the internet who passes Turnstile, was decoded inside that process. That process holds the database password, the Django secret key, the Google keys and a network path to everything. Decision 0120 narrowed the decoders a photo can reach, but a bug in one of them would still run with all of that in reach.

## Decision

- **A `public` service** from the same image, with its own gunicorn workers (3) and memory limit, serves `/health` and `/api/public/` only. It runs with `DIXIE_SERVICE=public`, which makes the app refuse every other path whatever the entrance header says. The `app` service serves the control app and keeps its own check of the public-path rule. Caddy sends the public door (8080) to `public` and the private door (8000) to `app`. `public` gets the app's secret files less the website's deploy hook, which it never uses. It starts once `app` is healthy, since `app` runs the migrations.
- **A `photo-worker` service** decodes every quote request photo. It is built from the same image but runs a small Django-free package, `photoworker`. It runs with `network_mode: none`, no secrets, no database, a read-only root, `cap_drop: [ALL]`, no-new-privileges, a 1 GiB memory limit, a process limit of 32, and its own user (10002, in the app's group for the two shared folders).
- **The handover:**
  - **Inbox:** the public service writes each upload to `photo-inbox`, a tmpfs volume shared with the worker only, as `ID.upload` (renamed from `.part` when complete).
  - **Decoding:** the worker takes uploads one at a time, oldest first. It decodes each in a fresh process with `PHOTO_DECODE_SECONDS` (20) to finish, writes the clean JPEG and then a one-line JSON result to `photo-outbox`, and deletes the upload either way.
  - **The answer:** the upload endpoint waits for the result, up to `PHOTO_DECODE_WAIT_SECONDS` (90), and answers the browser exactly as before. A decode that fails, crashes or runs out of time, or a worker that never answers, is a refused photo (`not_an_image`), as a bad photo always was.
  - **Clean-up:** nothing is left in either folder.
- **In development and tests** (no inbox set), the same decode runs in a fresh process in the app's own container, with the same time limit. So the existing photo tests exercise it, and new tests run the worker's own loop against throwaway folders.
- **Memory limits, from measurements** on 2026-11-22, idle and while decoding a 64-megapixel PNG (the largest photo allowed):

  | Service | Measured | Limit |
  | --- | --- | --- |
  | app | 203 MB | 768 MiB |
  | public | 188 MB | 768 MiB |
  | photo-worker | 11 MB idle, 624 MB at peak | 1 GiB |
  | calendar-worker | 63 MB | 384 MiB |
  | db | 54 MB | 2 GiB |
  | Caddy | 11 MB | 256 MiB |
  | cloudflared | 11 MB | 256 MiB |

  The limits total about 5.4 GB, leaving most of a 16 GB machine free.

## Alternatives considered

- **A second gunicorn on the same container.** Separates the workers, but not memory, restarts or secrets.
- **Decode in a subprocess of the public service.** It would still have the public service's network and secret files within reach.
- **A queue in PostgreSQL or Redis for the photos.** The worker would need a network and a database password, which is what this takes away. Files on tmpfs need neither.

## Consequences

A rush on the website no longer slows the control app, and a decoder bug finds no secret, no database and no network. Photos still never reach a disk before they are cleaned. Decoding adds about half a second per photo for starting the fresh process, and photos sent at the same moment wait their turn. There are two more containers to watch: `docker compose ps` shows them, and the troubleshooting guide covers a worker that is down.
