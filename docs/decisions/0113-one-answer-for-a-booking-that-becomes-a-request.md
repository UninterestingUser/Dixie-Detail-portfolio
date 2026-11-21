---
id: 113
title: "Every website booking that becomes a request gets one answer, which never mentions an existing booking"
summary: A booking past a confirmation cap, or for a number with a job that day, is answered request_instead with the day picked, and the site sends a request; no answer reveals a booking.
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

- **One answer.** A booking past either confirmation cap, or for a number that already has a job that day, is answered `409` `request_instead`, with the same message, "We can't book this time online. Send it as a request, with the day you picked, and we'll confirm by text or call.", and `preferred_day`, the date picked. Nothing is written, so no time is held.
- **The time is checked first,** for every booking, before the number is looked at, so a taken time is answered `time_taken` whatever the number holds.
- **The site sends the request a time form** in place of the booking, keeping everything entered, with the day and arrival picked as the preferred ones. It goes through Cloudflare's offline piece to `POST time-requests`, which tries the server at once, marked `from_booking`. The request lands on "needs you" as a booking request, and the owner books or declines it on the same screen as an offline request.
- **No more second vehicle requests.** The same-day case no longer makes a second vehicle request; any still waiting are approved or declined on their screen as before.
- **Every public answer checked:** quotes, open times, quote requests and offline requests answer the same whatever a number holds. The only answer that depends on a number's history is the booking's `confirmation` (decision 0112).

## Alternatives considered

- **Keep the second vehicle request, with a vaguer message.** The `202` with a request reference still differed from the cap answer, which tells the two apart.
- **Make the API record the request itself and answer "request received".** One step fewer for the customer, but it would book a request without the customer seeing it as one, and the owner asked for the request form with the day filled in.

## Consequences

- A second vehicle the same day now needs one more press from the customer, and arrives priced for the day like an offline request rather than at the quote they were shown. At launch this is only a second motorcycle.
- The site no longer needs its "second" confirmation screen.
