---
id: 124
title: "Control app sign-ins lock out after 5 failures in 15 minutes, by username and by address"
summary: "Five failed sign-ins for one username or from one address within 15 minutes refuse sign-ins for 15 minutes (settings), with a plain message; each lockout is logged and a manager can clear it."
date: 2026-11-22
area: control app
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [app/control/lockout.py, app/control/sign_in_views.py, caddy/Caddyfile, docs/reference/control-app.md, data/configuration.yaml, docs/decisions/0052-django-sign-in-over-tailscale.md]
---

# 0124: Control app sign-ins lock out after 5 failures in 15 minutes, by username and by address

**Status:** accepted · **Date:** 2026-11-22 · **Area:** control app

## Context

A review (finding L3) noted that the control app's sign-in had no limit on wrong passwords. Only the tailnet reaches it, but a stolen or lost staff phone on the tailnet could try passwords for as long as it liked.

## Decision

- **The limit.** After `SIGN_IN_LOCKOUT_FAILURES` (5) failed sign-ins for one username, or from one address, within `SIGN_IN_LOCKOUT_WINDOW_MINUTES` (15), sign-ins for that username or from that address are refused for `SIGN_IN_LOCKOUT_MINUTES` (15). All three are `.env` settings.
- **The refusal.** A refused attempt never checks the password, even a right one. It gets a plain message: "Too many failed sign-ins. Signing in is paused for 15 minutes. A manager can clear it sooner." A good sign-in clears that username's count.
- **Logging.** Each lockout is logged as "Sign-in lockout: username NAME after 5 failed sign-ins…" or "Sign-in lockout: address ADDRESS…", and so is each clearing.
- **Clearing.** On Account, **Sign-in lockouts**, a manager sees the lockouts in force and earlier ones, and can clear one. Clearing also removes the failures behind it, so the next typo doesn't lock it again at once.
- **The address.** Caddy works out the client's address on the private door, trusting only Docker's and the host's own ranges as proxies, and passes it in `X-Dixie-Client`. Tailscale's documentation doesn't say whether `tailscale serve` passes the client's address on. If it doesn't, all that reaches the app is a proxy's address on the server: loopback, or a private range of Docker's or the LAN's. Such an address isn't one person's, so it is never counted by address. Only the username limit applies, and one person's typos can't lock everyone out. The lockout screen and log show which addresses arrive.
- **Usernames** are matched without regard to case or surrounding spaces.

## Alternatives considered

- **django-axes.** Does this and more, but another dependency with its own tables and settings for a five-person staff.
- **Lock the account until a manager unlocks it.** Stronger, but one person's typos would stop work until a manager is free; a 15-minute pause is enough to make guessing hopeless.

## Consequences

Guessing a password over the tailnet becomes impractical. A staff member who mistypes five times waits 15 minutes or asks a manager. Failures older than the window are deleted as new ones come in; lockouts are kept as a record.
