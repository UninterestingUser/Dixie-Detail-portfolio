---
id: 90
title: "Addresses record how they were verified, and tax rates come from the state's boundaries, matched on the server and approved by the owner"
summary: "Each address stores its parts, coordinates, county and verification method; the server matches it to Tennessee's rate boundaries itself, and a changed rate waits for the owner's approval."
date: 2026-11-06
area: tax
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-06
supersedes: []
superseded_by: []
related: [docs/reference/sales-tax.md, docs/operations/addresses-and-sales-tax.md, docs/decisions/0025-sales-tax-by-service-address.md, docs/decisions/0032-address-validation-with-places.md, docs/decisions/0037-approved-out-of-area-addresses.md, app/billing/tax.py, app/billing/tax_rates.py, app/geo/verification.py]
---

# 0090: Addresses record how they were verified, and tax rates come from the state's boundaries, matched on the server and approved by the owner

**Status:** accepted · **Date:** 2026-11-06 · **Area:** tax

## Context

Decisions 0025, 0032 and 0037 set the rules: tax at the service address's rate from the state's boundary data, a county's rate and a flag when an address will not match, Census geocoding for addresses the owner types, and Georgia at a per-state 0%. Phase 3, Step 1 builds them. The open questions were how the server trusts an address from the website, where the boundary matching happens, and what a scheduled check may change on its own.

The Tennessee Department of Revenue's map service gives one area per city and one per county's unincorporated part, each with its local rate and situs code. Cities are cut out of their county's area. The service area's five counties come to 27 areas and about 150,000 boundary points.

## Decision

1. **Every address records how it was verified:** a Google place, the Census geocoder, or by hand, with the time, the coordinates and the county. Changing a part of a verified address clears its verification.
2. **The server looks up a website address itself.** The browser sends only the Google place ID and the autocomplete session token. The server calls Place Details with its own key and takes the parts and coordinates from Google's answer. Coordinates from a browser are never used.
3. **Boundaries are stored and matched on the server.** `import_tax_rates` stores each area's boundary as GeoJSON with its bounding box. A point is matched by checking the boxes, then the polygons, in plain Python, with no PostGIS. The database image stays the stock PostgreSQL image, and a match takes milliseconds.
4. **Every Tennessee county's rate is loaded,** not only the five counties'. Areas outside the five get a rate but no boundary, so an approved out-of-area Tennessee address takes its county's rate and is flagged, as for any address that will not match.
5. **A changed rate waits for the owner.** The import approves a jurisdiction's first rate, because there is nothing to compare it with and a job needs a rate. After that, any change found, by the import or by the morning check, is stored without approval and is never used until a manager approves it with its effective date. The check never changes a boundary or adds a jurisdiction; it reports them, and the owner runs the import.
6. **The morning check alerts through Healthchecks.** While a change waits for approval, the check exits with status 2 and its script sends the failure ping with the summary, so the owner gets an email; push alerts arrive in Phase 4. It runs daily so an approval clears the alert the next morning.
7. **State and local tax are rounded separately,** each to the cent, an exact half cent up, because the invoice and the remittance report show them separately.
8. **The per-state rate and the sourcing rule are settings.** Georgia's rate is a state-level jurisdiction with its own dated rates, seeded from `data/service-area.yaml` and then changed in the control app. The sourcing rule is a setting on the Location settings screen.

## Alternatives considered

- **Ask the state's map service for each address.** It would make booking depend on a state server being up, and cost a call per quote.
- **PostGIS.** It does the polygon test in the database, but it needs a different database image and a migration of the database for 27 polygons.
- **Apply rate changes automatically.** The state's data has no effective date, and a wrong rate would go straight onto customers' bills.
- **Use the latitude and longitude the browser gets from Google.** They could be altered in the browser to change the tax rate or pass the service-area check.

## Consequences

- At setup, and when the check reports a new area or changed boundaries, the owner runs `import_tax_rates`. Until the first import, every address is flagged and taxed at zero.
- Existing customer addresses get coordinates and jurisdictions from `verify_addresses`. Any it cannot match are left for the owner.
- The approval message counts the booked jobs a rate change affects. The push alert described in `sales-tax.md` waits for Phase 4.
