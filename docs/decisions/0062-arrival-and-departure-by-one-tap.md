---
id: 62
title: "Arrival and departure times are recorded by one tap"
summary: "At launch a push at the arrival time asks \"Arrived?\" and one tap records it, with \"Departed\" the same way; no background location. Automatic geofencing is a later Android add-on."
date: 2026-10-17
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md, docs/reference/control-app.md, docs/overview/roadmap.md, data/phases.yaml, docs/decisions/0023-time-to-leave-alert.md]
---

# 0062: Arrival and departure times are recorded by one tap

**Status:** accepted · **Date:** 2026-10-17 · **Area:** scheduling

## Context

Service times in the price matrix are the owner's estimates. Comparing them with the real time on site shows where they need adjusting, but only if arrival and departure are recorded with almost no effort. The control app is a web app on the Pixel.

## Decision

- **At launch, one tap.** A push at the scheduled arrival time asks "Arrived?", and one tap records it, from the notification or the job screen. A tap on the job screen also takes a single location reading to confirm the address. "Departed" works the same way, with a reminder at the expected end time. No background location.
- Each appointment stores its arrival and departure times and how each was recorded: tap, automatic or edited. Corrections are logged.
- With staff, times are recorded only at job addresses during their assigned jobs, with their agreement.
- The control app compares actual time on site with the estimate, to show where service times need adjusting.
- Built in Phase 4, with the time-to-leave alert (decision 0023) and "On my way".
- **Later add-on, not scheduled:** a small native Android companion app using Android geofencing: about 150 m around each job address, arrival after a few minutes inside, departure on exit. Alerts usually arrive within 2 minutes, up to 6 if the phone has been still. It needs the "Allow all the time" location permission and is installed directly, not from the Play Store.

## Alternatives considered

- **Automatic arrival from the web app.** A web app can't use location in the background, and browsers have no geofencing ([Android geofencing](https://developer.android.com/training/location/geofencing.html)).
- **Google Maps Timeline.** It is kept on the phone and shown only in the Maps app, so the system cannot read it.

## Consequences

Phase 4 adds two pushes per job and the arrival and departure fields. Each recorded time will note how it was recorded, with "automatic" among the choices, so the companion app can be added later without restructuring.
