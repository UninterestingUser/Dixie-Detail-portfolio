---
id: 101
title: "Website bookings in the control app: how matching, the four actions, requests and the needs-you list work"
summary: "Bookings and requests are matched, test numbers only to test records; requests hold new records back until booked; a second job on a day is a request; quote requests are priced by hand; one needs-you list."
date: 2026-11-08
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-18
supersedes: []
superseded_by: [docs/decisions/0107-default-staff-and-needs-you-for-decisions.md]
related: [docs/reference/returning-customers.md, docs/reference/control-app.md, docs/guides/handling-website-bookings.md, docs/decisions/0034-quiet-customer-matching.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md, docs/decisions/0061-staff-authorized-per-service.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0099-quote-requests-with-photos.md, docs/decisions/0100-public-api-quotes-and-bookings.md, docs/reference/public-api.md]
---

# 0101: Website bookings in the control app: how matching, the four actions, requests and the needs-you list work

**Status:** accepted; its "needs you" list is changed by [0107](0107-default-staff-and-needs-you-for-decisions.md): no new-booking or assign-staff items, one item per appointment · **Date:** 2026-11-08 · **Area:** booking

## Context

Phase 3, Step 5 builds quiet matching ([decision 0034](0034-quiet-customer-matching.md), [returning-customers.md](../reference/returning-customers.md)), the review queue, the assign-staff prompt for website bookings (decisions [0061](0061-staff-authorized-per-service.md) and [0069](0069-booking-staffing-and-publishing-in-the-control-app.md)), the screens for the requests Step 4 takes in, and a "needs you" list on the home screen. The owner set what each must do on 2026-11-08. The records leave open how a name or address is compared, what each of the four actions does to the record, how requests are matched, and how a second vehicle the same day is detected. Step 4's [decision 0100](0100-public-api-quotes-and-bookings.md) said each booking and request made a new customer until this step; that ends here.

## Decision

**Matching**

- **Bookings and every request are matched**, so a quote request, an offline request or a second vehicle lands on a returning customer's record too.
- **A customer's own number comes before a second contact's.** When several customers share a number, the one whose name the booking gave wins, then the one booked most recently.
- **Test numbers match only test customers, and real numbers only real ones**, so a smoke test never touches a real record.
- **Names.** Capitals, punctuation and extra spaces are ignored. A missing last name is not a difference. The name of any second contact on the record counts as a match.
- **Addresses.** Two addresses are the same when they have the same Google place, or the same street, unit and 5-digit ZIP once common words are shortened ("Street" and "St", "Northwest" and "NW").
  - A matched record address that was never verified takes the booking's verified location and tax, so the drive time and tax are right. Its parts are not changed.
- **Vehicles.** Make and model are compared on letters and digits only ("F-150" and "F150"), or by catalog model when both have one.
  - A vehicle picked from the photo cards with no make or model is always a different vehicle.
  - Vehicles the customer no longer has are left out. These are marked with a new "still the customer's" setting on each vehicle.
- **No flag when the record has nothing to compare.** A customer with no address or vehicle on file gets the booked one added without a flag.

**What the four actions do.** The job never changes price, tax or drive time, whatever the owner picks.

- **Name**
  - *Update the record:* the booked name replaces the record's.
  - *Keep the record:* nothing changes.
  - *Add alongside:* the booked name becomes a second contact with the booking's number, so the next booking under it matches without a flag.
- **Address**
  - *Update the record:* the booked address stays on the record and the record's other addresses are marked inactive.
  - *Keep the record:* the booked address stays on the job only.
  - *Add alongside:* both stay on the record.
- **Vehicle**
  - *Update the record:* the booked vehicle replaces the one picked, which is marked as no longer the customer's.
  - *Keep the record:* the booked vehicle stays on the job only.
  - *Add alongside:* both stay on the record.
- **Identical vehicles** ([decision 0067](0067-color-tells-identical-vehicles-apart.md))
  - *Update the record:* the job moves to the vehicle picked, and that vehicle takes the booking's color.
  - *Keep the record:* the job moves to the vehicle picked, which is left as it was.
  - In both cases the booking's own vehicle record is removed.
- **Move to a new customer.** The job goes to a new customer with the booking's name and number, along with the consent answers it brought. So do the address and vehicle it added; a record address or vehicle the booking matched is copied instead.
  - Every open flag on the job closes with this choice.
- **Logging.** Each choice is kept on its flag with who, when and a plain note of what it did, and each record change is kept in that record's change history.

**Requests**

- **Requests hold new records back.** An address or vehicle a request brings is kept off the record until the request is booked. Its flags are raised on the job then, so a declined request leaves the record as it was.
- **A second job on a day becomes a request.** When the matched customer already has a job, not canceled, on the day being booked, the booking becomes a request the owner approves. This covers the same vehicle booked twice, which is most likely a mistake.
  - The time must still pass the availability check. At launch only Motorcycle Detail and Monthly Maintenance share a day, so in practice this is a second motorcycle.
  - The website is told the booking is a request and that the owner will confirm. It is never told why beyond "there's already a booking for this number that day".
- **Quote requests are priced by hand into a quote**: one line with the price before tax, the time on site split into setup, service time and breakdown by the settings, and the tax at the request's address.
  - The quote is the price of record ([decision 0059](0059-quoted-price-is-price-of-record.md)). Pricing again makes a new quote.
  - Only a manager prices or declines.
- **Booking any request goes through the availability check**, as the website does, with the day locked. A manager can book outside a rule with a reason that is logged.
  - An offline request is priced for the day picked. The owner can honor the price the customer saw, recorded as an adjustment line with the reason.
- **Text links appear only with consent.** The request screens show a text link only when appointment-text consent is on record; otherwise the owner calls.

**The needs-you list and staff**

- **The list is per user.** "New website bookings" are those made since that user last tapped **Clear the new bookings**. Clearing stops at the newest booking the page showed, so one that came in meanwhile stays.
- **The assign-staff prompt** is any booked website job from now on with no one assigned.

## Alternatives considered

- **Match bookings only, and make requests new customers.** Leaves duplicate customers for the owner to merge by hand.
- **Let test bookings match real customers.** A smoke test from the owner's number would land on the owner's real record.
- **Update the record by rewriting the old address or vehicle in place.** Past jobs would then show the new address or vehicle. Marking the old one inactive keeps history true.
- **Raise a request's flags when it arrives.** A declined request would leave flags and records the owner must clean up.
- **Say nothing to the customer about a second vehicle and book it outright.** Goes against the owner's rule. Telling the customer it is a request does reveal that the number has a booking that day, but only to someone with the customer's phone number, a valid quote and a Turnstile pass, and it shows nothing from the record.
- **A "needs you" count shared by every user.** One person clearing it would hide new bookings from another.

## Consequences

Returning customers' website bookings land on their records with any difference waiting in one place, and nothing about a customer is ever shown on the website. The owner prices quote requests, books every kind of request, and handles them all from one list on the home screen. Push notifications for the list come in Phase 4; until then the Jobs calendar event on the phone is the alert for a new booking.
