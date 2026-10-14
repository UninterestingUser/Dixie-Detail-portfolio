---
title: Customer booking flow
summary: The seven steps a customer follows on the website to book a job, how the running estimate card behaves, and how address and phone entry are validated.
audience: [owner, staff, developer]
visibility: internal
status: planned
updated: 2026-10-13
tags: [booking, website, estimate-card, phase-3]
related: [docs/reference/pricing.md, docs/reference/scheduling-and-calendars.md, docs/reference/returning-customers.md, docs/reference/text-messages.md, docs/reference/website-and-seo.md]
---

# Customer booking flow

This is the Phase 3 design, approved in mockups on the design canvas "Dixie Detail Website Mockups". Until launch, customers book through Setmore.

The flow follows the Armstrong "Build Your Detail" screens the owner chose as a model, with a running estimate card, and goes one step further: it ends in a confirmed appointment instead of an estimate. Armstrong's wax-upgrade step is left out because ceramic wax is included in every detail.

## The seven steps

1. **Vehicle.** Year, then make, then model. A banner confirms the vehicle class, such as "Crossover identified", with that class's starting price. A doors, cab or third-row question appears only when the vehicle data cannot settle the size variant.
2. **Condition.** Three cards with plain descriptions. The first adds nothing, the second 10% and the third 20%.
3. **Service and add-ons.** Service cards show prices already adjusted for class, size and condition. Add-ons are tick boxes with their added price. Maintenance plans never appear here.
4. **Location.** The service address, validated as the customer types (see below). It is checked against the service area and sets the sales tax rate, with a reminder that water and power are needed.
5. **Date and time.** Only open days, and the three arrival times: 8:00, 8:30 or 9:00 AM.
6. **Details.** Name, mobile number, preferred payment method, and two unchecked consent checkboxes: appointment texts and follow-up texts. Nothing is charged.
7. **Review and confirm.** The full estimate, then a confirmation text (with consent) and a calendar file.

## How the steps behave

- The step indicator at the top is display only. It shows finished steps, the current step and grayed-out future steps; customers cannot jump ahead by clicking it.
- Only steps already reached are shown. Finishing a step reveals the next card below and scrolls to it. Earlier cards stay visible and can still be changed.
- "Start over" is a separate outlined button below the estimate card, not a text link.

## The estimate card

- **Always in view.** It sits beside the steps on a desktop, and becomes a navy bar pinned to the bottom of a phone screen that opens into a full sheet when tapped.
- **Builds line by line.** Vehicle and class, the service, the condition adjustment, each add-on, sales tax once the address is known, the total and the estimated job length. Before the address, the card says the total is before sales tax.
- **Shows "full day"** instead of hours for a job of 8 or more one-person hours.
- **Sets expectations.** It states that the final price is confirmed when the vehicle is seen, and that nothing is charged until the job is done.

## Address entry is validated as the customer types

The address field works like a Shopify checkout: suggestions appear as the customer types, and the address must be a real one. The system uses Google Places Autocomplete (New), restricted to US addresses and biased to the service area. Picking a suggestion returns verified address parts and coordinates, which drive the service-area check and the tax lookup. There is no separate "check" button. Addresses outside the service area are refused unless the owner has approved them. The Google Address Validation API may be added later to catch missing unit numbers.

## Phone number entry

The mobile number field formats itself as (###) ###-#### while the customer types and requires 10 digits. The number is stored as 10 digits and used for quiet matching; see [returning-customers.md](returning-customers.md).

## Other cases

- **A second vehicle the same day** is taken as a request the owner approves.
- **If the server is offline,** the site and prices still load, and the form becomes a "request a time" form that Cloudflare holds until the server returns.
