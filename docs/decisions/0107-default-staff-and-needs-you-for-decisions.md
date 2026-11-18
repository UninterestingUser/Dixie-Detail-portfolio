---
id: 107
title: "A default staff member is assigned to every new booking, and \"needs you\" holds only what needs a decision"
summary: "A setting names the person assigned to every new booking, Kris Grassman at launch; new bookings and staffing leave the needs-you list, which shows one item per appointment; quote request crews are checked by name."
date: 2026-11-18
area: control-app
status: accepted
audience: [owner, staff, developer]
visibility: internal
updated: 2026-11-18
supersedes: []
superseded_by: []
related: [docs/reference/control-app.md, docs/guides/assigning-staff.md, docs/guides/handling-website-bookings.md, docs/reference/scheduling-and-calendars.md, data/booking-rules.yaml, docs/decisions/0061-staff-authorized-per-service.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/decisions/0098-calendar-sync-queue-and-worker.md, docs/decisions/0101-website-bookings-in-the-control-app.md]
---

# 0107: A default staff member is assigned to every new booking, and "needs you" holds only what needs a decision

**Status:** accepted · **Date:** 2026-11-18 · **Area:** control-app

## Context

Decision 0061 assigned a one-person job automatically only when exactly one active staff member was qualified. Every other new job waited for an "Assign staff" item on the home screen. The "needs you" list (decision 0101) also listed each new website booking until it was cleared. With the owner on nearly every job, both items were noise, and a test booking showed two items for one appointment: "Assign staff" and "New booking".

## Decision

- **A default staff setting names who is assigned to every new booking,** from the website or the control app, whoever else qualifies and whatever the crew size. It is set to Kris Grassman. It is on the scheduling settings screen and seeded from `staff_assignment.default_staff` in `data/booking-rules.yaml`. The crew can still be changed on the job. This changes decision 0061's automatic assignment.
- **Without a default staff member,** or when that person is inactive or not authorized for the job's services, the decision 0061 rule still applies: the only qualified active person is assigned to a one-person job.
- **"Needs you" holds only what needs a decision:**
  - quote requests;
  - offline requests to price;
  - returning-customer differences, and a second vehicle the same day;
  - calendar clashes;
  - failed calendar syncs, listed once a job's push has failed three times in a row;
  - sales tax rates waiting for approval.

  A new booking is no longer an item, and neither is "Assign staff". The "Clear the new bookings" button and its marker go away.
- **An appointment has at most one item.** When several things need a decision on one job, the first item names the others ("Also: …").
- **The notice of a new booking** is the Jobs calendar event until Phase 4. From Phase 4, a push notification announces it.
- **On a quote request, Crew is a checkbox for each active staff member,** with the default staff checked. The people checked are assigned when the request is booked, and how many are checked is the crew size. Time on site is picked in 15-minute steps, shown as hours and minutes from 0:30 to 12:00.

## Alternatives considered

- **Keep the prompt, with the owner first in the list.** That is still one tap per booking for the same answer every time.
- **Assign the default staff only to one-person jobs.** A two-person job still needs the owner, and the second person is added on the job.

## Consequences

- A helper going alone is set on the job, replacing the default staff.
- The home screen stays empty unless something needs a decision, so an item there always means work.
