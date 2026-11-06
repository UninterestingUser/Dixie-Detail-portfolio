---
id: 91
title: "Google calls are counted and capped per day, drive times are cached by address pair and hour, and the home base lives in the database"
summary: "Every server call to Google is counted per Pacific day and refused past a daily cap set below Google's own limits; drive times are cached and fall back to a marked estimate."
date: 2026-11-06
area: maps
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-06
supersedes: []
superseded_by: []
related: [docs/decisions/0024-google-maps-platform.md, docs/decisions/0023-time-to-leave-alert.md, docs/reference/scheduling-and-calendars.md, docs/operations/addresses-and-sales-tax.md, app/geo/google.py, app/geo/drive.py]
---

# 0091: Google calls are counted and capped per day, drive times are cached by address pair and hour, and the home base lives in the database

**Status:** accepted · **Date:** 2026-11-06 · **Area:** maps

## Context

Google Maps Platform bills per call above its free monthly allowance. In Google Cloud the owner has limited each Places method to 322 calls a day and Routes to 161. A bug that looped, or an open-times search that asked for a drive time for every slot, could still run up a bill or hit those limits and have Google refuse calls mid-booking. The drive time also starts at the owner's home, which must never appear in the repository or the docs.

## Decision

1. **Every server call to an outside geocoding or routing service is counted** in the database per service and per day. Days are Pacific dates, because Google's daily limits reset at midnight Pacific time. The control app's Location settings screen shows the month's counts.
2. **Daily caps, set below Google's limits:** 300 Place Details calls and 150 Routes calls a day by default, both settings. Past a cap the call is not made: a drive time falls back to the estimate, and a place lookup is refused. The fallback therefore starts before Google would refuse.
3. **The cheapest tier for each call.** Place Details asks only for address components, formatted address and location, all Essentials fields; the place name would be billed at the Pro rate. The website's autocomplete session token is passed to Place Details, which ends the session, so the autocomplete requests before it are not billed. Routes asks only for duration and distance. It uses traffic-aware routing, which is the Pro tier, because traffic predicted for the time of day is the point of the drive time.
4. **Drive times are cached by address pair and hour of the day (Eastern)** for 30 days, a setting, so a search over many start times calls Routes once per pair and hour. Points are rounded to about a meter.
5. **The fallback is an estimate:** the straight-line distance times a road factor (1.3), at an average speed (40 mph), both settings. It is marked estimated wherever it is shown, and never cached, so the next request asks Google again.
6. **The home base is a database setting,** edited on the Location settings screen and checked with the Census geocoder, or entered as coordinates. It is backed up with the database and never written to the repository or the docs.
7. **The server key is optional.** Until the Bitwarden secret `GOOGLE_MAPS_SERVER_KEY` exists, the stack starts with an empty key file and the app runs without Google: drive times are estimated and website place lookups are refused.

## Alternatives considered

- **Rely on Google's limits alone.** Google would refuse calls at the limit, but the app would not know in advance, and a booking could fail halfway.
- **Count by Eastern day.** It would let two Eastern days' calls fall in one Pacific day and exceed Google's limit.
- **Proxy address autocomplete through the server** so it could be counted. That would add a fourth public API endpoint, and the public API does only three things. Autocomplete stays in the browser with the public key, and Google's own daily limit caps it.
- **Cache by exact departure time.** Nearly every slot would miss the cache.

## Consequences

- Expected calls per website booking: one Place Details call when the customer picks the address, with the autocomplete requests before it free under session pricing, plus one Routes call for the drive from the home base when the pair and hour are not already cached. Later steps add a call for the drive between two jobs on the same day, and the morning refresh of the time-to-leave alert in Phase 4.
- A day with very heavy use falls back to estimated drive times. The jobs it books show "Estimated" beside the drive time.
