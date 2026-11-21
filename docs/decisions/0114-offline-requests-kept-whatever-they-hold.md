---
id: 114
title: "Offline requests are kept whatever they hold, and the replay Worker reports to Healthchecks"
summary: "The server keeps every signed, readable offline request, listing any problem for the owner, and the replay Worker pings a Healthchecks check that fails when a request is refused or stuck."
date: 2026-11-21
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/decisions/0100-public-api-quotes-and-bookings.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/reference/public-api.md, docs/operations/monitoring.md, docs/guides/previewing-and-deploying-the-website.md, app/publicapi/lenient.py, app/publicapi/time_requests.py, site/shared/offline.js, site/workers/offline-replay/index.js]
---

# 0114: Offline requests are kept whatever they hold, and the replay Worker reports to Healthchecks

**Status:** accepted · **Date:** 2026-11-21 · **Area:** website

## Context

A review (finding M5) found two ways an offline request could be lost without anyone knowing. The server checked a replayed request as strictly as a live form, so a problem with its content refused it: a quote that had expired by the replay, a vehicle or service the catalog no longer has, an address it couldn't match, or a malformed phone number. The Worker then parked it under `refused:` in Workers KV, where nobody looks. And nothing said when the Worker stopped running, or when one request kept failing while the server was up.

## Decision

- **Kept whatever it holds.** `POST time-requests` and `POST quote-requests/offline` accept every request that carries a valid signature and can be read. Each field is read on its own (`publicapi/lenient.py`). One that can't be read is left empty, and its problem is listed on the request with the others (address not matched, not priced, a field missing or not used). The body exactly as it arrived is kept beside it whenever anything couldn't be read, and shown on the request's screen. The request shows on "needs you" with "something to check".
- **Refused only:** a bad signature (`401`, checked before the body is read), a body that isn't JSON or an object (`400`), and one with no usable `request_id` (`400`), since a second replay couldn't be told from the first. A request sent twice is stored once, as before.
- **A number that can't be read** matches no customer and records no consent. A missing name is kept as "(no name given)".
- **The replay Worker reports** after each run to the Healthchecks check whose ping address is the Worker secret `HEALTHCHECKS_OFFLINE_URL` (from Bitwarden, put with `wrangler secret put`). It pings success when nothing is refused or stuck, and the `/fail` address when any request sits under `refused:`, or has waited more than an hour to reach the server while the server's `/health` answers. A Worker that stops running stops pinging, which the check alerts on. The time a request was held goes in its KV key's metadata, so the run sees it from the key list alone. The ping and the log carry counts only, never a request.

## Alternatives considered

- **Refuse, and have the owner read `refused:`.** That is how requests were lost: nobody reads KV.
- **Alert from the server instead.** The server can't see requests that never reach it, nor a Worker that stopped.
- **Alert on any request held over an hour.** An outage would alert every hour; the "public address" check already covers an outage, so a held request only counts as stuck while the server answers.

## Consequences

- An offline request can arrive with empty fields; the owner reads its problems and the body as sent, and contacts the customer.
- The Worker makes two KV list calls a run, 576 a day, inside the free plan's 1,000, and calls `/health` only when something old is still held.
- A request refused before this change stays under `refused:` and fails the check until it is read and its key deleted.
- The owner adds the Healthchecks check and the Worker secret once ([monitoring.md](../operations/monitoring.md#the-offline-requests-check)).
