---
id: 46
title: "Control app screens are Django pages with htmx, mobile-first and installable"
summary: "The control app is server-rendered Django pages with htmx, designed for the phone first and installable to its home screen; the Django admin is for superusers only."
date: 2026-10-14
area: control-app
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/control-app.md, docs/decisions/0001-postgresql-and-django.md, docs/decisions/0052-django-sign-in-over-tailscale.md]
---

# 0046: Control app screens are Django pages with htmx, mobile-first and installable

**Status:** accepted · **Date:** 2026-10-14 · **Area:** control-app

## Context

The owner runs the business from a Google Pixel 9a on the job and from Fedora workstations at the desk. Phase 1 builds the first control app screens. The project has one developer working mostly through Claude Code, so every extra build tool or codebase is a cost.

## Decision

- Control app screens are Django templates rendered on the server. htmx updates parts of a page, such as marking a job paid, without a full reload. There is no separate JavaScript application and no front-end build step.
- Every screen is designed for a phone-width screen first, then widened for the desktop.
- The control app is installable: it has a web app manifest and the other parts Chrome on Android needs to add it to the home screen and open it in its own window. The tailnet address already serves HTTPS, which installation requires.
- The Django admin is for superusers only, for fixing data by hand. Staff and day-to-day work use the control app screens.

## Alternatives considered

- **A JavaScript single-page app (React or similar).** Adds a build pipeline, a second codebase and a private API that would all need securing and testing.
- **The Django admin as the main interface.** Shows every table rather than the owner's tasks, is awkward on a phone, and is hard to narrow to what a helper should see.
- **A native Android app.** Needs installing and updating on each device, and does nothing for the Fedora workstations.

## Consequences

One codebase and one language for the app. Pages work without installing anything. Interactions that need heavy client-side logic, such as a drag-and-drop calendar, would need a new decision. The htmx file will be served by the app itself, so the control app makes no calls to outside sites.
