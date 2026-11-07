---
id: 92
title: "A typed address the Census geocoder cannot find is searched with Google and used only if it agrees, or its location is set by hand"
summary: "When the Census map lacks a street, Google's match is kept only if its house number, street and ZIP code agree; otherwise the owner pastes the location from Google Maps, recorded with who set it."
date: 2026-11-06
area: maps
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-06
supersedes: []
superseded_by: []
related: [docs/decisions/0090-tax-rates-from-the-state-boundaries.md, docs/decisions/0091-google-calls-counted-capped-and-cached.md, docs/reference/sales-tax.md, docs/operations/addresses-and-sales-tax.md, app/geo/verification.py, app/geo/google.py, app/geo/management/commands/verify_addresses.py]
---

# 0092: A typed address the Census geocoder cannot find is searched with Google and used only if it agrees, or its location is set by hand

**Status:** accepted · **Date:** 2026-11-06 · **Area:** maps

## Context

An address the owner types is verified with the Census Bureau's geocoder ([decision 0090](0090-tax-rates-from-the-state-boundaries.md)). The Census map is updated slowly, so a correct address on a street in a newly built neighborhood comes back unmatched from `verify_addresses` and from the control app's address form. Until now the owner could only mark such an address verified by hand with its county. Without coordinates it could not be matched to a rate boundary, so it took the county's rate and was flagged.

Google usually has the new street. But a geocoder that always returns its nearest guess can quietly put an address on the wrong street or in the wrong ZIP code, and with it the wrong city's tax rate.

## Decision

1. **Google is asked only when the Census geocoder finds no match.** The server calls Places Text Search (New) with the typed address, asking only for place IDs (field mask `places.id`, Google's IDs Only tier). It then looks up the one best match with Place Details, asking only for address components, formatted address and location, as for a website address. There is no autocomplete session, so the Place Details call is billed on its own.
2. **A Google match is used only if it agrees.** Its house number, street and ZIP code must equal the stored address's, after both streets are put in one form: capitals, no punctuation, the usual USPS abbreviations ("Road" as "RD", "Southeast" as "SE", "First" as "1ST") and any unit dropped. Otherwise the address stays unmatched, and the reason names the parts that differ. The owner's own spelling is kept. Google gives the coordinates, the county and the place ID, and the method is recorded as "Google address search".
3. **Both calls count against daily caps.** Text Search has its own cap, `text_search_daily_cap` (300 a day by default, below the 322 a day set in Google Cloud for each Places method), and Place Details counts against its existing cap. When Google cannot be asked (no key, a cap reached, no answer), the address stays unmatched with that reason, and `verify_addresses` stops asking Google for the rest of the run. A Census geocoder that cannot be reached leaves the address "not checked" without asking Google, so an outage does not spend Google calls.
4. **Otherwise the owner sets the location by hand.** In the control app the owner pastes the latitude and longitude that Google Maps copies when a spot is right-clicked. The point must be in the United States, which also catches the two numbers pasted the wrong way round. The address is marked "Location set by hand" and records who set it (`verified_by`); the change history also records the user and the reason. Coordinates are now required: an address can no longer be verified by hand with only its county.
5. **The tax comes from the location either way.** Census, Google and by hand all end the same way: the coordinates are matched against the Tennessee boundaries, which also give the county, and the county rate and flag remain the fallback.
6. **`verify_addresses` reports how each address matched:** by Census, by Google, or set by hand. It reports by customer and address ID only, as before. A location set by hand is reported and kept, even with `--all`. An address marked by hand with no location, such as one carried over from the old "verified" flag, is checked like an unverified one. `--no-google` uses the Census geocoder only.

## Alternatives considered

- **Use Google for every typed address.** It costs a Place Details call per address, and the free Census geocoder matches most of them.
- **Accept Google's best match as it is.** Google answers with its nearest guess, such as the next house number or the same street name in the next town. A wrong point means a wrong tax rate on an invoice, so a guess is not good enough.
- **Places Autocomplete instead of Text Search.** It returns several predictions meant for someone typing; Text Search's IDs Only tier returns the best match for a whole address at no charge.
- **Keep county-only verification by hand.** The address would keep taking the county rate and the flag. With a location pasted from Google Maps, it matches its city or unincorporated area like any other address.

## Consequences

- A typed address in a new neighborhood usually verifies without the owner's help, at the cost of one Place Details call.
- A `verify_addresses` run asks Google for each address the Census geocoder misses, in a dry run too, so a large first run can reach the day's cap; the rest wait for the next run.
- Addresses marked by hand before this change have no location. The next `verify_addresses` run checks them; any it cannot match keep their county and take its rate, flagged, until the owner pastes their location.
- A rural address written as "Highway 60" may not agree with Google's "TN-60" and stays unmatched; the owner sets its location by hand.
