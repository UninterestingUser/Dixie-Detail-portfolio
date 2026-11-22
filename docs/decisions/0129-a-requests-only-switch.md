---
id: 129
title: "A requests-only switch pauses online booking while the request form keeps working"
summary: "ops/site-mode.sh requests makes the booking and quote endpoints answer 503, which the website treats as server unavailable, while the offline request endpoints keep working."
date: 2026-11-22
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [docs/decisions/0100-public-api-quotes-and-bookings.md, docs/reference/public-api.md, docs/operations/moving-production.md, docs/operations/when-its-down.md, ops/site-mode.sh, app/publicapi/site_mode.py]
---

# 0129: A requests-only switch pauses online booking while the request form keeps working

**Status:** accepted · **Date:** 2026-11-22 · **Area:** website

## Context

Moving production, restoring a backup or fixing part of the system can leave the server answering while bookings shouldn't be taken: a booking made on the old host during a move would be lost when the new host's restore starts. The website already has a path for this: when the API doesn't answer, or answers 5xx, the booking form becomes a "request a time" form that Cloudflare holds and replays (decision 0100).

## Decision

- **`ops/site-mode.sh requests [REASON]`** sets the website's mode to requests, a row in the database (`SiteMode`, pk 1), so it lasts through restarts until `ops/site-mode.sh normal`. With no argument it shows the mode.
- **In requests mode** every public API path answers `503` with `{"error": "requests_only", ...}` and `Retry-After: 600`, except the two the offline form and the offline quote request reach (`time-requests` and `quote-requests/offline`). The website treats the 503 as "server unavailable" and offers the request form from the first step. Cloudflare's held requests still reach the server. The 503 carries the CORS headers, so the browser reads it. The health page is outside `/api/public/`, so the public health check stays green, and the control app is never affected.
- **Used for** maintenance, the move to a new host, and outages of a part the booking flow needs.

## Alternatives considered

- **Stop the public service.** Cloudflare's held requests would then wait too, and the health check would page the owner.
- **A Caddy rule.** It would need a Caddy reload to switch, and the mode wouldn't be visible to the app.

## Consequences

- Requests made in requests mode reach the owner as time requests, to confirm by text or call, as during an outage.
- Forgetting to switch back leaves booking paused; the moving and outage guides end with `ops/site-mode.sh normal`.
