---
title: Handling website bookings
summary: How to work through the home screen's "needs you" list - calls to confirm new customers, differences from the record, requests, calendar problems and tax rates - and try it with test records.
audience: [owner, staff]
visibility: internal
status: current
updated: 2026-11-21
tags: [guides, booking, website, matching, requests, control-app]
related: [docs/decisions/0112-confirming-bookings-from-new-customers.md, docs/decisions/0113-one-answer-for-a-booking-that-becomes-a-request.md, docs/decisions/0107-default-staff-and-needs-you-for-decisions.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md, docs/reference/control-app.md, docs/reference/returning-customers.md, docs/reference/public-api.md, docs/decisions/0101-website-bookings-in-the-control-app.md, docs/decisions/0099-quote-requests-with-photos.md, docs/guides/assigning-staff.md, docs/guides/booking-a-job.md]
---

# Handling website bookings

Website bookings land in the control app on their own. They are matched to returning customers by mobile number, put on the Jobs calendar, and given to the default staff, Kris Grassman at launch ([assigning-staff.md](assigning-staff.md#the-default-staff-on-every-new-booking)). Only what needs a decision is on the home screen, under **Needs you**, newest first, with a count ([decision 0107](../decisions/0107-default-staff-and-needs-you-for-decisions.md)). Tap an item to open the screen that handles it. One job has at most one item: when several things need you on it, the item ends "Also: …" with the others.

## A new booking is not a "needs you" item

A new website booking needs no decision, so it isn't listed, and neither is assigning staff. Until Phase 4 brings push notifications, which will announce new bookings, the Jobs calendar event on your phone is the notice of a new booking. The exception is a new customer who didn't agree to texts: that booking needs a call (below).

## Confirming a new customer's booking

A booking from someone who has never had a completed job holds its time but isn't confirmed yet ([decision 0112](../decisions/0112-confirming-bookings-from-new-customers.md)). It is yellow in every schedule view, on its page and on the Jobs calendar, with the reason:

- **Waiting for a text reply.** The customer ticked the text box, so they were asked by text to reply YES. From Phase 4 a YES confirms it by itself. Until then no text actually goes out, so call them as below.
- **Call to confirm.** They didn't tick the box. The booking is under **Needs you** at once as **Call to confirm**, with **Call** (and **Text**, only if they agreed to texts some other time).

Call, confirm the day, then tap **Mark confirmed**, with a note if it helps, such as "Confirmed by phone". It turns the normal color everywhere, the Jobs calendar included. Only a manager can mark a job confirmed. If they don't want it after all, cancel it as usual ([booking-a-job.md](booking-a-job.md)).

The banner at the top of the Schedule screen lists unconfirmed jobs that start within 48 hours, each with **Call**, **Text** and **Mark confirmed**, so none is missed the day before. The 48 hours, and the caps below, are on **Account → Scheduling settings**, under **Confirming new customers**.

**The caps.** One new number can hold one unconfirmed booking, and five new customers can be waiting at once. Past either, the website doesn't book: it takes the booking as a request, which arrives as a **Booking request** (below), and tells the customer you'll confirm by text or call. A booking for a number that already has a job that day gets the same answer. The website never tells the customer which reason it was; the request's screen tells you.

## Check the booking: differences from the record

A returning customer's booking goes on their record even when the name, address or vehicle differs. **Check the booking** opens the differences, the booked version beside the record's. The job keeps the address and vehicle as booked whatever you choose, so its price, tax and drive time never change. For each difference, tap one:

- **Update the record.** The new name replaces the old one. A new address becomes the customer's address, and the old one is marked inactive. A new vehicle replaces the vehicle you pick, which is marked as no longer theirs.
- **Keep the record.** Nothing on the record changes; the booked address or vehicle stays on this job only.
- **Add alongside.** A second address, another vehicle, or the booked name as a second contact, so the next booking under it matches without a difference.
- **Move the booking to a new customer.** Use this when someone else shares the phone number, such as a family member. The job, with the address, vehicle and text consent answers the booking gave, goes to a new customer with the name it gave.

**Which vehicle?** means the customer has two vehicles with the same make, model and year, and the color they typed didn't pick one. Pick the vehicle it was. **It was this vehicle; record the color** also saves the color they gave on that vehicle, so it picks itself next time. If it was really a third vehicle, tap **Add it as another vehicle**.

Every choice is logged with your name and the time. **Account → Review queue** lists every booking with a difference still open.

## Quote requests

A quote request is a job the website can't price: a full-size van, or a Full Detail or Interior Only at condition Level 3. The screen shows the vehicle, the service wanted with any condition level and add-ons, what the customer says is needed, their photos (tap one to see it full size), the address with the drive from home and its tax rate, their preferred days, and their number.

1. **Price it** (managers), in the **Price** section: pick the **Service** and **Vehicle class**, then enter the **Price before tax**, pick the **Time on site** in hours and minutes (0:30 to 12:00, in 15-minute steps, setup and breakdown included), and tick the **Crew**: one or two people, the default staff ticked to start. The people ticked are assigned when it's booked, and how many you tick is the crew size; at least one of them must be authorized for the service. For a Level 3 request the price covers the whole job, add-ons included, and the Level 2 price is shown above the form for reference. **Save the price** makes a quote with the sales tax added; it keeps the request's condition level and add-ons when you price the service the customer asked for. That quote is the price the job is booked at. Pricing again makes a new quote.
2. **Send the price yourself,** by text or call, until Phase 4's texts. **Text** opens your messages with the price filled in, starting "Dixie Detail:". It appears only when the customer agreed to appointment texts; otherwise call.
3. **Book it** when the customer picks a day: enter the date and arrival time. The time is checked against the scheduling rules like any booking; see [booking-a-job.md](booking-a-job.md#book-off-hours) for booking off hours. The job shows the description and photos, so whoever does it sees them.
4. Or **Decline it** with a reason, and tell the customer yourself. Photos are deleted 90 days after the request is declined, or its job is done or canceled.

If you booked the job by mistake, remove it with **Cancel job → Created by mistake**: the request comes back to **Needs you**, marked "priced, not booked", with its price, description and photos, ready to book again. Canceling the job (customer or Dixie Detail) closes the request.

## Offline requests

An offline request was sent while the server was down, or while Google's address suggestions were, so nothing is booked. When the customer typed the address, the screen says it wasn't checked: check it with them before booking. The screen shows today's price beside the price the customer saw, and says when they differ. Enter the date and time, which start at the time the customer wanted, and tap **Book**. The job is priced for that day. Tick **Honor the price the customer saw** to book it at their price instead. Or decline it with a reason.

## Booking requests

A booking request is a website booking taken as a request instead of a job ([decision 0113](../decisions/0113-one-answer-for-a-booking-that-becomes-a-request.md)). The screen says why: **Another job that day**, when a returning customer books a second vehicle, such as a second motorcycle, on a day they already have a job; or **Past the limit on unconfirmed bookings**, when a new number is past one of the caps above. The customer was told only that you'll confirm by text or call. The time isn't held, so call or text them soon. **Approve and book** books it at the price they were shown, at the time they picked or another. Or decline it with a reason, and let them know.

## Time Off, calendar sync and sales tax

**Time Off over a booked job** opens the calendar notes on the home screen: keep, reschedule or cancel the job. **Calendar sync failing** is a job the app has failed to put on the Jobs calendar three times in a row; it keeps trying, and the job opens so you can check it. The fix is in [troubleshooting.md](../operations/troubleshooting.md#a-job-shows-calendar-sync-failing-under-needs-you). **New sales tax rate** opens **Sales tax**, to approve the rate with its date or reject it.

## Try it with test records

On the server, the smoke test can leave test records for you to practice on ([public-api.md](../reference/public-api.md#test-records)):

```
cd /srv/dixie-detail
docker compose run --rm --no-deps -T app python manage.py api_smoke_test --scenario returning --keep
docker compose run --rm --no-deps -T app python manage.py api_smoke_test --scenario quote --keep
```

The first makes a test customer, "Smoke Test", with two identical RAV4s, and books three jobs: one with a new address, one with no color, one with a color that matches neither. The second sends a full-size van quote request with two photos. Each shows a "Test" badge. Try the actions, then remove everything with:

```
docker compose run --rm --no-deps -T app python manage.py delete_test_records
```
