---
id: 68
title: "The control app learns HTTPS from Caddy, serves its own static files and needs sign-in on every page"
summary: "Caddy tells the app that tailnet requests are HTTPS, so cookies are secure and sign-in passes the origin check; WhiteNoise serves static files; every page but a few needs sign-in."
date: 2026-10-18
area: control-app
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-18
supersedes: []
superseded_by: []
related: [docs/reference/control-app.md, docs/architecture/network-and-access.md, docs/guides/installing-the-control-app.md, docs/decisions/0046-control-app-django-htmx.md, docs/decisions/0052-django-sign-in-over-tailscale.md, docs/decisions/0038-two-doors-access-model.md]
---

# 0068: The control app learns HTTPS from Caddy, serves its own static files and needs sign-in on every page

**Status:** accepted · **Date:** 2026-10-18 · **Area:** control-app

## Context

The first control app screens (decision 0046) needed sign-in (decision 0052) to work at the tailnet address. `tailscale serve` ends HTTPS and passes each request to Caddy's control-app port, and Caddy passes it to the app over plain HTTP. Without being told otherwise, Django would take every request as plain HTTP: it would refuse to rely on secure cookies, and its check that a form was posted from the same site compares the browser's `https://` origin against an `http://` address. The pages also need a stylesheet, icons and htmx, but the app container's file system is read-only and the stack has no web server for files.

## Decision

- **HTTPS from Caddy.** Caddy's control-app port, reached only through `tailscale serve`, sets `X-Forwarded-Proto: https` on every request. Django trusts that header (`SECURE_PROXY_SSL_HEADER`); only Caddy can reach the app, and Caddy's public port sets the header from its own plain connection, so a visitor cannot fake it.
- **Secure cookies.** The session and form-check (CSRF) cookies are marked Secure, and the session cookie is hidden from scripts.
- **Trusted origins from the allowed hosts.** The origins a form may be posted from are `https://` plus each name in `DJANGO_ALLOWED_HOSTS`, except `localhost` and `127.0.0.1`. There is no separate setting to keep in step.
- **Static files from the app.** WhiteNoise serves the stylesheet, icons and htmx straight from the app's folders, after the public-door check, so the public door never serves them. htmx 2.0.11 is kept in the repository, so the control app calls no outside site.
- **Sign-in on every page.** Django's login-required middleware covers every page. The only exceptions are the health page, the sign-in page, and the three files Chrome fetches to install the app and show the offline page: the manifest, the service worker and the offline page itself. None of them shows business data.
- **No customer data on the device.** The service worker caches only the offline page; every other page always comes from the server.

## Alternatives considered

- **Trust the `X-Forwarded-Proto` that `tailscale serve` sends, through Caddy's trusted proxies.** Depends on which Docker network address the request comes from, which can change; the control-app port is HTTPS-only anyway.
- **Caddy serves the static files from a shared volume.** Needs a collect step on every deploy and another volume, for a handful of files.
- **A separate trusted-origins setting.** One more value in `.env` that must match `DJANGO_ALLOWED_HOSTS`.
- **htmx from a public CDN.** A call to an outside site on every page, which decision 0046 rules out.
- **A service worker that caches pages for offline use.** Would keep customers' details on the phone, where a lost phone could show them.

## Consequences

Sign-in works at the tailnet address with no extra setting: adding a name to `DJANGO_ALLOWED_HOSTS` also trusts it for sign-in. Opening the control app by any other address fails the sign-in check by design. A new page needs sign-in unless its view is marked otherwise. Updating htmx means replacing the file in `app/control/static/control/` and the name in the base template.
