---
id: 112
title: "A new customer's website booking holds its time but waits to be confirmed, within two caps"
summary: "Website bookings from numbers with no completed job are unconfirmed until a text reply or a manager confirms them, at most one per number and five at once; known customers and control app bookings are confirmed at once."
date: 2026-11-21
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/reference/booking-flow.md, docs/reference/public-api.md, docs/reference/control-app.md, docs/reference/text-messages.md, docs/reference/scheduling-and-calendars.md, docs/guides/handling-website-bookings.md, app/appointments/confirmation.py, data/booking-rules.yaml, data/message-templates.yaml, docs/decisions/0034-quiet-customer-matching.md, docs/decisions/0108-one-text-consent.md]
---

# 0112: A new customer's website booking holds its time but waits to be confirmed, within two caps

**Status:** accepted · **Date:** 2026-11-21 · **Area:** booking

## Context

A review (finding H1) pointed out that anyone with a phone number, real or made up, could book every open day through the website, and each booking was a confirmed job that blocked the calendar. The site takes no payment or card, so nothing stops a prank, a competitor or a bot that gets past Turnstile. The owner wants new customers to be able to book a real time online, without letting a stranger fill the calendar.

## Decision

- **Confirmation state on every appointment:** confirmed or unconfirmed. An unconfirmed job has a reason: "waiting for a text reply" (the customer ticked the text consent box) or "call to confirm" (they didn't). A confirmed job records how (known customer, booked in the control app, text reply, or marked by a manager, with an optional note), when and by whom. The change history keeps every change, as for the rest of the appointment. Every job that exists before this is confirmed (migration `appointments/0013_confirmation`).
- **Confirmed at once:** a website booking whose number quietly matches a customer with at least one completed job, and every booking made in the control app, a website request booked there included. Every other website booking is unconfirmed. It still holds its time: it is a real appointment either way.
- **Two caps, scheduling settings:** at most one open unconfirmed booking per new customer's number, and at most five open unconfirmed new-customer bookings at once. "Open" means booked, not confirmed, starting from now on. Past either cap the API doesn't book (decision 0113). Test records count only against test records. The caps are counted under a lock of their own.
- **The confirmation request text is queued, not sent:** with text consent, the booking stores an outgoing message of kind "confirmation request" for Phase 4's sender: "Dixie Detail: Please confirm your {service} on {day, date} at {time}. Reply YES to confirm, or call or text (423) 380-9120 to change it. Reply STOP to opt out." For Phase 4: a reply of YES, Y or CONFIRM, in any case, punctuation ignored, confirms that number's soonest unconfirmed appointment; any other reply goes on "needs you" as a message; an undeliverable confirmation text puts the job on "needs you" at once.
- **Call to confirm:** a booking without text consent goes on "needs you" at once, with call and text links and **Mark confirmed**.
- **What the customer sees:** with text consent and a new number, "Check your phone. We've texted you to confirm your appointment. Reply YES to confirm it."; without consent, "We'll call you to confirm your appointment."; a known customer, the confirmation as before. The API returns the state (`confirmation`), and the site picks the words. Until Phase 4 sends texts the first message is shown anyway, because the site isn't public before then.
- **Control app:** unconfirmed jobs are yellow in every schedule view and on the job page, with the reason. A banner at the top of the Schedule screen lists those that start within 48 hours (a setting), each with call and text links and **Mark confirmed**. Managers can mark any job confirmed.
- **Jobs calendar:** an unconfirmed job's event uses Google's Banana event color and goes back to the normal color once confirmed. A color changed by hand in Google is put back, like any other edit.
- **Texting registration and the Text Message Terms** name requests to confirm a new booking. The consent checkbox wording doesn't change: "confirmations" already covers it.

## Alternatives considered

- **Hold new bookings as requests the owner approves.** Safe, but a new customer could never book a real time online, which is the point of the booking page.
- **A deposit or card on file.** Card details never touch the server, and the business takes payment only when the job is done.
- **A one-time code by text before booking.** Needs the texting service, which can't send until carrier registration is approved (Phase 4), and adds a step for every customer.
- **Caps only, without confirmation.** Limits the damage, but the owner still can't tell a real new booking from a prank.

## Consequences

- The `confirmation` value in the booking answer tells the person booking whether the number belongs to a past customer. It needs a real booking, with Turnstile, to find out, and the owner accepted it so a known customer sees the usual confirmation.
- Until Phase 4 no confirmation text is sent, so every new customer's booking is confirmed by a call. The banner keeps those starting soon in sight.
- Existing tests that book one made-up number many times lift the caps in their shared setup; the caps are tested at their launch values in `publicapi/test_confirmation.py`.
- The smoke test's returning customer gets one completed test job, so its three bookings are confirmed and uncapped.
- The owner's color edits on Jobs events are now restored at the next check, because the color carries the confirmation.
