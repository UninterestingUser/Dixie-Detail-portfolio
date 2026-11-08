---
id: 102
title: "A job booked from a website request: removing it reopens the request, canceling it closes it"
summary: "Removing a job as created by mistake keeps every quote something else refers to and sends its request back to the owner; canceling it closes a quote request, whose photos then follow the 90-day rule."
date: 2026-11-08
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-08
supersedes: []
superseded_by: []
related: [docs/decisions/0095-canceling-and-removing-jobs.md, docs/decisions/0099-quote-requests-with-photos.md, docs/decisions/0101-website-bookings-in-the-control-app.md, docs/reference/scheduling-and-calendars.md, docs/reference/control-app.md, docs/reference/public-api.md]
---

# 0102: A job booked from a website request: removing it reopens the request, canceling it closes it

**Status:** accepted · **Date:** 2026-11-08 · **Area:** booking

## Context

[Decision 0095](0095-canceling-and-removing-jobs.md) lets a manager remove a job created by mistake, with its quotes when nothing else uses them. Step 5 ([decision 0101](0101-website-bookings-in-the-control-app.md)) books jobs from quote requests, whose hand-priced quote the request keeps. Removing such a job tried to delete that quote and failed, and `delete_test_records` failed with it, leaving the test job on the schedule. The owner set the rules below on 2026-11-08.

## Decision

- **A quote is deleted only when nothing refers to it.** That means no job, no quote request, no offline request and no other record. Change history doesn't count. Its own lines and website number go with it. A quote whose website number a second vehicle request still holds is kept.
- **Removing a job as created by mistake deletes only the job.** A quote request it was booked from goes back to open, with its quote, description and photos, and returns to the "needs you" list, marked "priced, not booked". It can be booked again from the same quote. An offline request or a second vehicle request booked as that job goes back to open the same way.
- **Canceling such a job, by the customer or by Dixie Detail, closes its quote request** as canceled. Its photos are deleted 90 days later, as for any closed request ([decision 0099](0099-quote-requests-with-photos.md)).
- **`delete_test_records` works in an order that never trips a protected reference.** It removes the jobs first, then the requests and their photos, then the quotes they were priced from. Its report counts the quotes.

## Alternatives considered

- **Delete the request with the job.** The owner's pricing, the description and the photos would be lost over a booking mistake.
- **Leave the request marked booked with no job.** It would drop out of every list and never close, so its photos would be kept forever.

## Consequences

A booking mistake on a quote request costs nothing: rebook it from the same quote. Test records from every smoke test scenario can always be deleted.
