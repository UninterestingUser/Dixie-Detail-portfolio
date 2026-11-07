---
title: Sales tax
summary: How sales tax is added at the rate for the customer's service address, how the rate is found and kept current, how approved out-of-area addresses are treated, and how collected tax is tracked until remitted.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-06
tags: [sales-tax, tennessee, georgia, compliance]
related: [docs/decisions/0090-tax-rates-from-the-state-boundaries.md, docs/decisions/0091-google-calls-counted-capped-and-cached.md, docs/decisions/0092-google-fallback-and-locations-set-by-hand.md, docs/operations/addresses-and-sales-tax.md, docs/decisions/0059-quoted-price-is-price-of-record.md, data/service-area.yaml, docs/decisions/0025-sales-tax-by-service-address.md, docs/decisions/0037-approved-out-of-area-addresses.md, docs/reference/bookkeeping-gnucash.md]
---

# Sales tax

Sales tax is added on top of the final price at the rate for the customer's service address. It appears as its own line on the estimate, the invoice and the receipt. This is the owner's decision. Since Phase 3, Step 1, every quote issued with a service address carries the tax line, and the control app shows it on each job; the invoice, the receipt and the remittance reports come in later steps. This page is not tax advice.

## Tennessee rates

Tennessee charges 7% statewide, and local governments add up to 2.75%. The state's data on 2026-11-06 listed local rates of 2.75% in Bradley, McMinn and Polk counties and their cities, 2.25% in Hamilton County and all its cities (Chattanooga included, 9.25% combined), and 2% in Meigs County. The system does not rely on these figures: it loads the state's own data, described below. The 7% state rate is in [data/service-area.yaml](../../data/service-area.yaml).

## Verified addresses

Every address records its parts, its map coordinates, its county and how it was verified ([decision 0090](../decisions/0090-tax-rates-from-the-state-boundaries.md)):

- **Google place.** A website address arrives as the Google place ID the customer picked. The server looks the place up itself with its own key and takes the parts, coordinates and county from Google's answer. Coordinates sent from a browser are never trusted.
- **Census geocoder.** An address the owner types in the control app is checked with the Census Bureau's free geocoder when it is saved.
- **Google address search.** The Census map lacks streets in newly built neighborhoods. When the geocoder finds no match, the server asks Google's Text Search for the address, then looks up its best match with Place Details, asking only for address components, formatted address and location. The match is used only if its house number, street and ZIP code agree with the typed address, after both are written the same way ("Road" as "Rd", "Southeast" as "SE", any unit dropped). Otherwise the address stays unmatched. The owner's spelling is kept; Google gives the coordinates and county. Both calls count against Google's daily caps ([decision 0092](../decisions/0092-google-fallback-and-locations-set-by-hand.md)).
- **Location set by hand.** For an address neither finds, the owner pastes its latitude and longitude from Google Maps. The address is marked "Location set by hand" and records who set it; the change history records it too.

An address that none of these verifies is not saved. Whichever way it is verified, the tax comes from its location and the Tennessee boundaries (below), which also give its county.

Changing the street, unit, city, state or ZIP code of a verified address clears its verification, so it is checked again. `python manage.py verify_addresses` checks every existing customer address the same way and reports how each matched: by Census, by Google or set by hand. See [../operations/addresses-and-sales-tax.md](../operations/addresses-and-sales-tax.md).

## Finding the rate for a service address

1. A Tennessee address's coordinates are matched against the Tennessee Department of Revenue's tax rate boundaries to find its city, or its county's unincorporated area, and that area's rate. Each city is cut out of its county's area, so a point is in only one.
2. If an address will not match, or has no coordinates, it takes its county's rate and is flagged for the owner to check before the invoice goes out. The flag shows on the customer's address, on the job and on the control app's Sales tax screen.
3. An address outside Tennessee takes its state's per-state rate (below).

The tax is worked out on the taxable amount at the approved rate in effect on the day of service: the state tax and the local tax are each rounded to the cent, an exact half cent up. The quote stores the taxable amount, the state and local rates, each tax, the jurisdiction and the flag.

The control app's booking form shows the tax line as soon as a service address is picked. On the website, the estimate card will show it once the address is entered; before that it says the estimate is before sales tax.

## Keeping rates current

The state publishes its rate boundaries as a map service, updated quarterly, with each area's local rate.

- `python manage.py import_tax_rates` loads, for the five counties, every city's and unincorporated area's rate and boundary, and for every other Tennessee county its county rate without a boundary, so an approved out-of-area Tennessee address can take its county's rate. A jurisdiction's first rate is approved as it is loaded. Run it by hand at setup and when the check reports a new area or changed boundaries.
- **The morning check.** `dixie-tax-rate-check.timer` runs `import_tax_rates --check` every day at 5:15 AM. It compares the state's rates with the stored ones and stores any change to wait for the owner's approval. It never changes a rate in use, a boundary or a jurisdiction. While a change waits, the check's Healthchecks ping fails, so the owner gets an email ([../operations/monitoring.md](../operations/monitoring.md)).
- **Approving a change.** On the Sales tax screen, a manager approves a waiting rate with the date it takes effect, or rejects it. The rate before it ends the day before. A waiting rate is never used, and a rejected one is not flagged again.
- Each job is taxed at the rate in effect for its address on the day of service. If a rate changes after a job is booked, the new rate applies to its invoice, and the approval message counts the booked jobs it affects. The price before tax never changes ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)). A push alert with the booked total beside the new one comes with push notifications in Phase 4.

## Approved out-of-area addresses

The owner can mark any address outside the five counties as an exception. Today that is one customer just over the state line in Cohutta, Georgia, where the service is performed.

- The address passes the service-area check, can book online and gets normal drive times.
- It is charged no Tennessee tax, because the work happens in Georgia.
- Georgia generally does not tax detailing labor (Georgia letter ruling LR SUT-2019-11, on car wash charges), so its rate is kept as a per-state setting at 0%. The import seeds it from [data/service-area.yaml](../../data/service-area.yaml); after that a manager changes it on the Sales tax screen, with the date a new rate takes effect.
- The owner is to confirm both points with the accountant, and ask whether Georgia work creates a Georgia income tax filing.

## The sourcing rule is one setting

Charging the service address's rate is the owner's decision. The state's guidance for in-state sellers describes the business-location rate for shipped goods, and how it treats mobile services could not be confirmed. The rule is therefore a single setting, "Tax sourcing" on the control app's Location settings screen, in case the accountant ever advises the business-location rate instead. With the business-location rule, every job takes the home base's rate.

## Tracking tax until it is remitted

- Every quote and invoice stores the taxable amount, state tax, local tax and jurisdiction.
- Tips are kept out of the taxable amount, and promotions reduce it. Tips are recorded on payments, never as priced lines, so they never reach the taxable amount; promotion lines take their discount off it.
- The control app will show tax collected and not yet remitted, and a report per filing period broken down by jurisdiction (Phase 6).
- Tax never counts as income. It posts to Liabilities:Sales Tax Payable in GnuCash and clears when the owner remits it. See [bookkeeping-gnucash.md](bookkeeping-gnucash.md).

## Sources

- [Tennessee local sales tax](https://www.tn.gov/revenue/taxes/sales-and-use-tax/local-sales-tax.html) and the [state boundary map service](https://tnmap.tn.gov/arcgis/rest/services/COMMUNITY/REVENUE_TAX_RATE_BOUNDARIES/MapServer)
- [SUT-29 on in-state sellers](https://revenue.support.tn.gov/hc/en-us/articles/360058174652-SUT-29-Online-Sales-by-In-State-Sellers)
- [Georgia letter ruling LR SUT-2019-11](https://ezel.ai/tax-rulings/ga/lr-sut-2019-11-car-wash-service)
