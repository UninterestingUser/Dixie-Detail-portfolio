---
title: Sales tax
summary: How sales tax is added at the rate for the customer's service address, how the rate is found and kept current, how approved out-of-area addresses are treated, and how collected tax is tracked until remitted.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [sales-tax, tennessee, georgia, compliance]
related: [data/service-area.yaml, docs/decisions/0025-sales-tax-by-service-address.md, docs/decisions/0037-approved-out-of-area-addresses.md, docs/reference/bookkeeping-gnucash.md]
---

# Sales tax

Sales tax is added on top of the final price at the rate for the customer's service address. It appears as its own line on the estimate, the invoice and the receipt. This is the owner's decision; the system applies it from Phase 3. This page is not tax advice.

## Tennessee rates

Tennessee charges 7% statewide, and local governments add up to 2.75%. A June 2026 rate table listed 9.75% combined across the service area, except Chattanooga at 9.25%. The system does not rely on those figures: it uses the state's own rate and boundary data, described below.

## Finding the rate for a service address

1. The verified address from the booking form gives map coordinates. Addresses entered by the owner are turned into coordinates with the Census Bureau's free geocoder.
2. The coordinates are matched against the Tennessee Department of Revenue's tax rate boundary data to find the city or county and its rate.
3. If an address will not match, the job takes its county's rate and is flagged for the owner to check before the invoice goes out.

The estimate card shows the tax line as soon as the address is entered; before that it says the estimate is before sales tax.

## Keeping rates current

The state publishes rate tables and boundary data, and its boundary map service is updated quarterly. A scheduled job compares stored rates with the state's and flags any change for the owner's approval. Each job is taxed at the rate in effect for its address on the day of service, so a rate change flows into booked jobs without a prompt.

## Approved out-of-area addresses

The owner can mark any address outside the five counties as an exception. Today that is one customer just over the state line in Cohutta, Georgia, where the service is performed.

- The address passes the service-area check, can book online and gets normal drive times.
- It is charged no Tennessee tax, because the work happens in Georgia.
- Georgia generally does not tax detailing labour (Georgia letter ruling LR SUT-2019-11, on car wash charges), so its rate is kept as a per-state setting at 0%.
- The owner is to confirm both points with the accountant, and ask whether Georgia work creates a Georgia income tax filing.

## The sourcing rule is one setting

Charging the service address's rate is the owner's decision. The state's guidance for in-state sellers describes the business-location rate for shipped goods, and how it treats mobile services could not be confirmed. The rule is therefore a single setting, in case the accountant ever advises the business-location rate instead.

## Tracking tax until it is remitted

- Every invoice stores the taxable amount, state tax, local tax and jurisdiction.
- Tips are kept out of the taxable amount, and promotions reduce it.
- The control app shows tax collected and not yet remitted, and a report per filing period broken down by jurisdiction.
- Tax never counts as income. It posts to Liabilities:Sales Tax Payable in GnuCash and clears when the owner remits it. See [bookkeeping-gnucash.md](bookkeeping-gnucash.md).

## Sources

- [Tennessee local sales tax](https://www.tn.gov/revenue/taxes/sales-and-use-tax/local-sales-tax.html) and the [state boundary map service](https://tnmap.tn.gov/arcgis/rest/services/COMMUNITY/REVENUE_TAX_RATE_BOUNDARIES/MapServer)
- [SUT-29 on in-state sellers](https://revenue.support.tn.gov/hc/en-us/articles/360058174652-SUT-29-Online-Sales-by-In-State-Sellers)
- [Georgia letter ruling LR SUT-2019-11](https://ezel.ai/tax-rulings/ga/lr-sut-2019-11-car-wash-service)
