---
title: Returning customers and quiet matching
summary: How a new booking is linked to an existing customer by mobile number without showing the customer anything, and how the owner resolves differences in the control app.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [customers, booking, matching, privacy]
related: [docs/decisions/0034-quiet-customer-matching.md, docs/reference/booking-flow.md, docs/architecture/data-model.md]
---

# Returning customers and quiet matching

Returning customers are matched quietly by phone number when a booking is submitted. The booking flow looks the same to everyone, and nothing from a customer's record is ever shown on the website. This is the owner's decision of 2026-10-11, built in Phases 1 and 3.

## How quiet matching works

1. The booking's mobile number (10 digits, formatting ignored) is checked against every customer's number and every second contact's number.
2. A match puts the appointment on that customer's record. No match creates a new customer.
3. A booking under a second contact's own name and number (for example, a spouse listed on the record) matches without a flag.
4. When the name, address or vehicle differs from the record, the appointment still books, and the control app flags it with both versions side by side.
5. A vehicle with the same make and model, and the same year when both have one, counts as the same vehicle. Anything else is added to the customer's vehicles and flagged.
6. The job always uses the address and vehicle on the booking, so drive time, sales tax and price are right whatever the owner decides later.

## How the owner resolves a flagged difference

For each difference the owner chooses one of four actions:

- **Update the record** with the new name, address or vehicle.
- **Keep the record** as it is.
- **Add alongside:** a second address or another vehicle.
- **Move the booking to a new customer,** when a different person shares the phone number.

## Why nothing is shown to the customer

Showing saved details after someone types a phone number would reveal a customer's address and vehicle to anyone who knows their number. Quiet matching gets the record keeping right without that risk.

## Deferred until after launch

Texted sign-in codes, a "Booked with us before?" shortcut, remembered devices and personal rebooking links were considered and deferred by the owner.
