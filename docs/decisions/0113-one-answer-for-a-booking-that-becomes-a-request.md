---
id: 113
title: "Every website booking that becomes a request gets one answer, which never mentions an existing booking"
summary: A booking past a confirmation cap, or for a number with a job that day, is kept as a booking request with its quote and answered the same way every time, so no answer reveals a booking.
date: 2026-11-21
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/decisions/0112-confirming-bookings-from-new-customers.md, docs/decisions/0101-website-bookings-in-the-control-app.md, docs/reference/public-api.md, docs/reference/booking-flow.md, docs/reference/returning-customers.md, docs/reference/control-app.md, app/publicapi/bookings.py]
---

# 0113: Every website booking that becomes a request gets one answer, which never mentions an existing booking

**Status:** accepted · **Date:** 2026-11-21 · **Area:** booking

## Context

A review (finding L1) found that a booking for a number that already had a job that day was answered "Because there's already a booking for this number that day, we'll confirm this one by text or call." Anyone could type a stranger's number and learn whether that person had a detail booked that day. The confirmation caps (decision 0112) add more cases where a booking can't go through, each of which could leak the same way if they were answered differently.

## Decision

- **One answer.** A booking past either confirmation cap, or for a number that already has a job that day, is answered `202` with its request number, `status: "requested"`, the same message, "Thanks! We've got your request for this time. We'll confirm it by text or call. Your request number is …", and the summary built only from this booking. The site shows the message under "Request received".
- **The server keeps the request itself,** as a booking request (the `SecondVehicleRequest` model, which keeps its first name), with the quote the customer saw, the time they picked and the reason, which only the owner sees: another job that day, or past the limit on unconfirmed bookings. It holds no time. Its address and vehicle wait off the customer's record until it is booked. The owner approves it, which books that quote as issued (decision 0059), confirmed as booked in the control app, or declines it.
- **The time is checked first,** for every booking, before the number is looked at, so a taken time is answered `time_taken` whatever the number holds.
- **Every public answer checked:** quotes, open times, quote requests and offline requests answer the same whatever a number holds. The only answer that depends on a number's history is the booking's `confirmation` (decision 0112).

## Alternatives considered

- **Keep the same-day request with a vaguer message, and answer capped bookings differently.** The two answers would still tell the cases apart.
- **Answer `request_instead` and have the site send the request a time form, with the day filled in.** The first version of this change did that. The customer pressed Send twice, and the request was priced again on arrival instead of keeping the quote the customer saw. The owner chose the server-side request instead (2026-11-21).

## Consequences

- A booking past a cap still reaches the owner, with its price, without the customer doing anything more.
- Requests aren't capped: someone who fills the caps can keep sending requests, but they hold no time and need Turnstile and the rate limit, and the owner declines them.
- "Second vehicle the same day" is now "Booking request" in the control app, covering both reasons.
