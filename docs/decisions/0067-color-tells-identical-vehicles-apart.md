---
id: 67
title: "An optional color tells a returning customer's identical vehicles apart"
summary: "An optional Color box picks between a returning customer's vehicles of the same make, model and year; a blank or unmatched color still books and is flagged. Color never affects the price."
date: 2026-10-18
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-18
supersedes: []
superseded_by: []
related: [docs/reference/returning-customers.md, docs/reference/booking-flow.md, docs/decisions/0034-quiet-customer-matching.md, docs/decisions/0059-quoted-price-is-price-of-record.md]
---

# 0067: An optional color tells a returning customer's identical vehicles apart

**Status:** accepted · **Date:** 2026-10-18 · **Area:** booking

## Context

Quiet matching (decision 0034) puts a booking on a returning customer's existing vehicle when the make and model match, and the year too when both have one. Some customers have two vehicles with the same make, model and year, and the booking form asks for nothing else, so it cannot tell which one is being booked. The Baserow import met the same problem and needed hand fixes. The owner set this rule on 2026-10-18; it is planned for Phase 3, with the booking form.

## Decision

- The booking form's vehicle step gets an optional Color box, free text.
- When the matched customer has more than one vehicle with the booking's make, model and year, a color that matches exactly one of them, ignoring capital letters and extra spaces, puts the appointment on that vehicle.
- When the color is blank or matches none of them, the appointment still books, and the control app asks the owner which vehicle it was, with the same difference flag used for a changed name, address or vehicle.
- When only one vehicle matches, the color does not change the match.
- Color never affects the price or the time. It is not a price input, and the estimate card does not show it.

## Alternatives considered

- **Ask the customer to pick from their saved vehicles.** Would show a customer's vehicles to anyone who knows their phone number, which quiet matching exists to prevent.
- **Ask for the license plate or VIN.** Tells vehicles apart for certain, but most customers do not know them by heart and it adds a step to every booking.
- **Make color required.** Adds friction for the many customers with one vehicle of each kind, and a mistyped color would still need the owner.
- **Always flag identical vehicles for the owner.** Works, but leaves the owner a question the customer could usually have answered.

## Consequences

Most bookings for a customer with identical vehicles land on the right record without the owner. A wrong or missing color costs only a flag, never a lost booking or a different price. The color is compared with the vehicle's recorded color, so imported vehicles without one will be flagged until the owner fills it in.
