---
title: Returning customers and quiet matching
summary: How a new booking is linked to an existing customer by mobile number without showing the customer anything, and how the owner resolves differences in the control app.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-18
tags: [customers, booking, matching, privacy]
related: [docs/decisions/0034-quiet-customer-matching.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md, docs/reference/booking-flow.md, docs/architecture/data-model.md]
---

# Returning customers and quiet matching

Returning customers are matched quietly by phone number when a booking is submitted. The booking flow looks the same to everyone, and nothing from a customer's record is ever shown on the website. This is the owner's decision of 2026-10-11, built in Phases 1 and 3.

## How quiet matching works

1. The booking's mobile number (10 digits, formatting ignored) is checked against every customer's number and every second contact's number.
2. A match puts the appointment on that customer's record. No match creates a new customer.
3. A booking under a second contact's own name and number (for example, a spouse listed on the record) matches without a flag.
4. When the name, address or vehicle differs from the record, the appointment still books, and the control app flags it with both versions side by side.
5. A vehicle with the same make and model, and the same year when both have one, counts as the same vehicle. Anything else is added to the customer's vehicles and flagged. When the customer has more than one such vehicle, the color picks between them (see below).
6. The job always uses the address and vehicle on the booking, so drive time, sales tax and price are right whatever the owner decides later.

## Telling identical vehicles apart by color

Some customers have two vehicles with the same make, model and year, such as two of the same truck. The make, model and year cannot say which one is being booked, so in Phase 3 the booking form's vehicle step will have an optional Color box ([decision 0067](../decisions/0067-color-tells-identical-vehicles-apart.md)).

- **One identical vehicle matches the color.** When the matched customer has more than one vehicle with the booking's make, model and year, and the booking's color matches the recorded color of exactly one of them, the appointment goes on that vehicle with no flag. Capital letters and extra spaces will be ignored, so "dark blue" matches "Dark Blue".
- **The color is blank or matches none of them.** The appointment still books, and the control app will flag it with the same difference flag as a changed name, address or vehicle, listing the customer's identical vehicles for the owner to say which one it was. The owner can also add it as another vehicle.
- **Only one vehicle matches the make, model and year.** The match is made as in step 5, and the color does not change it.
- **Color never affects the price.** The price and time come from the booking's vehicle class, size variant, condition and services, so which identical vehicle the owner picks never changes them.

## How the owner resolves a flagged difference

For each difference the owner chooses one of four actions:

- **Update the record** with the new name, address or vehicle, or, for a flag about identical vehicles, pick the vehicle it was.
- **Keep the record** as it is.
- **Add alongside:** a second address or another vehicle.
- **Move the booking to a new customer,** when a different person shares the phone number.

## Why nothing is shown to the customer

Showing saved details after someone types a phone number would reveal a customer's address and vehicle to anyone who knows their number. Quiet matching gets the record keeping right without that risk.

## Deferred until after launch

Texted sign-in codes, a "Booked with us before?" shortcut, remembered devices and personal rebooking links were considered and deferred by the owner.
