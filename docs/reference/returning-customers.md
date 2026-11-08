---
title: Returning customers and quiet matching
summary: How a website booking or request is matched to a customer by mobile number without showing anything, how a second vehicle the same day becomes a request, and how the owner resolves differences.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-11-08
tags: [customers, booking, matching, privacy]
related: [docs/decisions/0101-website-bookings-in-the-control-app.md, docs/guides/handling-website-bookings.md, docs/reference/control-app.md, docs/reference/public-api.md, docs/decisions/0034-quiet-customer-matching.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md, docs/reference/booking-flow.md, docs/architecture/data-model.md]
---

# Returning customers and quiet matching

Returning customers are matched quietly by phone number when a booking is submitted. The booking flow looks the same to everyone, and nothing from a customer's record is ever shown on the website. This is the owner's decision of 2026-10-11 ([decision 0034](../decisions/0034-quiet-customer-matching.md)). It is built (Phase 3, Step 5): website bookings, quote requests, offline requests and a second vehicle the same day are all matched, and the control app's review queue resolves each difference. How the details are compared and what each action does are in [decision 0101](../decisions/0101-website-bookings-in-the-control-app.md); the steps for the owner are in [../guides/handling-website-bookings.md](../guides/handling-website-bookings.md). The public API's answers are built only from the quote, the address and the booking itself, so matching changes nothing a customer sees.

## How quiet matching works

1. The booking's mobile number (10 digits, formatting ignored) is checked against every customer's number and every second contact's number. A customer's own number comes first. When several customers share the number, the one whose name the booking gave comes first, then the one booked most recently. A test number matches only test customers, and a real number only real ones.
2. A match puts the appointment on that customer's record, with the consent answers the booking gave. No match creates a new customer.
3. A booking under a second contact's own name and number (for example, a spouse listed on the record) matches without a flag. So does a booking from the customer's number under the name of any second contact on the record.
4. When the name, address or vehicle differs from the record, the appointment still books, and the control app flags it with both versions side by side. Capitals, punctuation and extra spaces never count as a difference, nor does a missing last name; "100 Example Street Northwest" and "100 Example St NW" are the same address. A customer with no address or vehicle on file gets the booked one added without a flag.
5. A vehicle with the same make and model, and the same year when both have one, counts as the same vehicle ("F-150" and "F150" are the same model). Anything else is added to the customer's vehicles and flagged; a vehicle picked from the photo cards with no make or model typed is always flagged. Vehicles marked as no longer the customer's are left out. When the customer has more than one such vehicle, the color picks between them (see below).
6. The job always uses the address and vehicle on the booking, so drive time, sales tax and price are right whatever the owner decides later. A record address that matched but was never verified takes the booking's verified location and tax; its street and city are left as they were.

## Requests are matched too

A quote request, an offline "request a time" form and a second vehicle the same day are matched the same way when they arrive, and go on the matched customer. An address or vehicle a request brings is kept off the record until the request is booked; its flags are raised on the job then. A declined request leaves the record as it was.

## A second vehicle the same day

When the matched customer already has a job that day (not canceled), a website booking for that day comes in as a request the owner approves or declines, not an appointment. The time must still be open. At launch a day takes one job, and only Motorcycle Detail and Monthly Maintenance share a day, so in practice this is a second motorcycle. The website tells the customer the booking is a request and that Dixie Detail will confirm it by text or call ([public-api.md](public-api.md#booking-post-bookings)).

## Telling identical vehicles apart by color

Some customers have two vehicles with the same make, model and year, such as two of the same truck. The make, model and year cannot say which one is being booked, so the booking form's vehicle step has an optional Color box ([decision 0067](../decisions/0067-color-tells-identical-vehicles-apart.md)).

- **One identical vehicle matches the color.** When the matched customer has more than one vehicle with the booking's make, model and year, and the booking's color matches the recorded color of exactly one of them, the appointment goes on that vehicle with no flag. Capital letters and extra spaces are ignored, so "dark blue" matches "Dark Blue".
- **The color is blank or matches none of them.** The appointment still books, on a vehicle record of its own, and the control app flags it with the same difference flag as a changed name, address or vehicle, listing the customer's identical vehicles for the owner to say which one it was. The owner can also add it as another vehicle.
- **Only one vehicle matches the make, model and year.** The match is made as in step 5, and the color does not change it.
- **Color never affects the price.** The price and time come from the booking's vehicle class, size variant, condition and services, so which identical vehicle the owner picks never changes them.

## How the owner resolves a flagged difference

Each flag offers four actions in the review queue (**Account → Review queue**, the job's page, or the "needs you" list on the home screen):

- **Update the record** with the new name, address or vehicle. A new address becomes the customer's address and the old one is marked inactive; a new vehicle replaces the one the owner picks, which is marked as no longer the customer's. For a flag about identical vehicles, pick the vehicle it was: the job moves to it, and it takes the color the booking gave.
- **Keep the record** as it is. The booked address or vehicle stays on the job only. For identical vehicles, pick the vehicle it was, and its record is left unchanged.
- **Add alongside:** a second address, another vehicle, or the booked name as a second contact.
- **Move the booking to a new customer,** when a different person shares the phone number. The job, and the address, vehicle and consent answers the booking brought, go to a new customer with the booking's name and number; every open flag on the job closes.

Every choice is logged on its flag with who made it, when and what it did, and every record change is kept in that record's change history.

## Why nothing is shown to the customer

Showing saved details after someone types a phone number would reveal a customer's address and vehicle to anyone who knows their number. Quiet matching gets the record keeping right without that risk.

## Deferred until after launch

Texted sign-in codes, a "Booked with us before?" shortcut, remembered devices and personal rebooking links were considered and deferred by the owner.
