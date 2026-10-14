---
id: 38
title: "Two doors into the app: private over Tailscale, public through the tunnel"
summary: "Caddy serves the whole app on 127.0.0.1:8000 for Tailscale, and only /health and /api/public/ on port 8080 inside Docker for the Cloudflare Tunnel."
date: 2026-10-12
area: network
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/network-and-access.md]
---

# 0038: Two doors into the app: private over Tailscale, public through the tunnel

**Status:** accepted · **Date:** 2026-10-12 · **Area:** network

## Context

Staff need the whole app; the internet must reach only the health page and the booking API.

## Decision

One reverse proxy with two listeners. `tailscale serve --bg 8000` publishes the private door; the tunnel route `api.dixiedetail.com` points at `http://caddy:8080`. No other ports are published.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Nothing new listens on the LAN, and guessing paths on the public address returns "not found".
