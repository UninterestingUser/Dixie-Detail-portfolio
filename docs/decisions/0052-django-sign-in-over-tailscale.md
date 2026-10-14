---
id: 52
title: "Django sign-in, reachable only over Tailscale"
summary: "Each person signs in to the control app with their own Django account, and the sign-in page, like the rest of the control app, is reachable only over Tailscale."
date: 2026-10-14
area: security
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/architecture/network-and-access.md, docs/decisions/0005-tailscale-private-access.md, docs/decisions/0038-two-doors-access-model.md, docs/decisions/0046-control-app-django-htmx.md]
---

# 0052: Django sign-in, reachable only over Tailscale

**Status:** accepted · **Date:** 2026-10-14 · **Area:** security

## Context

Tailscale decides which devices can reach the control app (decisions 0005 and 0038), but not which person is using the device. Helpers will join later, the change history (decision 0050) needs to name the person who made each change, and a lost or shared phone should not open the business's records.

## Decision

- Every control app page and the Django admin require a signed-in user, using Django's built-in accounts, passwords and sessions.
- Each person has their own account. Superusers are the owner and developers (decision 0046).
- The sign-in page is part of the control app, so it is served only through the private door over Tailscale. The public door answers only `/health` and `/api/public/`, so the sign-in page cannot be reached from the internet.
- Passwords are stored by Django as salted hashes, never as text.

## Alternatives considered

- **Tailscale alone.** Any device on the tailnet would have full access, and changes could not be traced to a person.
- **Tailscale identity headers from `tailscale serve`.** Ties every app account to a tailnet account and trusts a header for identity.
- **A public sign-in page.** Exposes the control app to the internet; rejected in decision 0005.

## Consequences

Two layers protect the control app: the tailnet and a personal sign-in. Session cookies are marked secure, since the tailnet address is HTTPS. There is no emailed password reset at first; the owner resets a password with `python manage.py changepassword`.
