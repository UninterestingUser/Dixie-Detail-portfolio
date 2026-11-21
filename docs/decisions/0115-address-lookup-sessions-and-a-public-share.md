---
id: 115
title: "Website address lookups need a Turnstile-opened session and stop at a public share of the daily cap"
summary: "POST addresses needs a lookup session opened with a Turnstile token (about 10 lookups in 30 minutes), and website lookups stop at a public share of the Place Details cap, keeping a reserve for the control app."
date: 2026-11-21
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/decisions/0091-google-calls-counted-capped-and-cached.md, docs/decisions/0092-google-fallback-and-locations-set-by-hand.md, docs/reference/public-api.md, docs/reference/booking-flow.md, docs/reference/control-app.md, app/publicapi/lookups.py, app/geo/google.py]
---

# 0115: Website address lookups need a Turnstile-opened session and stop at a public share of the daily cap

**Status:** accepted · **Date:** 2026-11-21 · **Area:** website

## Context

A review (finding L2) noted that `POST addresses` needed no Turnstile check, only the rate limit, and each call is a Place Details call the business pays for past the free amount. A script spread over a few addresses could use up the whole daily cap (decision 0091) in minutes. Then the control app couldn't look addresses up either, and neither could offline requests arriving.

## Decision

- **Lookup sessions.** `POST addresses` needs a `lookup_session`. The site opens one with `POST addresses/sessions` and a Turnstile token when the customer reaches the location step. A session allows `ADDRESS_LOOKUP_SESSION_LOOKUPS` lookups (10) within `ADDRESS_LOOKUP_SESSION_MINUTES` (30), settings in `.env`. A lookup without a live session is refused `403` `lookup_session`; the site opens a new one and tries once more, out of sight. The rate limit stays on top, with its own kind for opening sessions.
- **A fresh token for submitting.** Turnstile tokens are used once, so once the session is open the site keeps a fresh token ready for the Book button, out of sight, as the quote request card does for photos.
- **A public share of the Place Details cap.** The day's cap (300) is split: website lookups stop at the public share (250), and the rest is the reserve for the control app and the server's own address checks, such as an offline request looked up when it arrives. Both are on the location settings screen, and the share can't be set above the cap. Website calls are counted separately in the day's usage.
- **Past the share,** a lookup is answered `429` `lookups_used_up`, and the site takes a typed address and the request a time form, as when Google's suggestions fail. The control app's Schedule screen says the day's public lookups ran out.

## Alternatives considered

- **Turnstile on every lookup.** A visible check could pop up each time a customer corrects their address, and each token is used once anyway.
- **A lower overall cap.** It would hit the control app just as hard as the website.
- **Charge the reserve only after the share.** The reserve exists so the owner's own work never waits on the website's traffic.

## Consequences

- Opening the session costs one Turnstile check at the location step; a customer who sits on the page more than 30 minutes gets a new session at the next lookup.
- The smoke test opens a lookup session too, from its one-time pass.
- On a day the share runs out, website customers send requests with typed addresses, which the owner checks.
