---
id: 94
title: "How the availability check places a later job, counts a shared day and lets a manager override"
summary: "A later job is offered at its placed start; a shared day holds up to the largest per-service maximum; owner bookings and moves are checked, with a logged manager override."
date: 2026-11-07
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-07
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md, data/booking-rules.yaml, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0093-quarter-hour-rounding-confirmed.md, docs/decisions/0072-motorcycles-class.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md]
---

# 0094: How the availability check places a later job, counts a shared day and lets a manager override

**Status:** accepted · **Date:** 2026-11-07 · **Area:** scheduling

## Context

Decision 0056 lists the six conditions of the availability check. Building it in Phase 3, Step 2 needed a few smaller choices the conditions leave open. At launch the start times are 8:00, 8:30 and 9:00, but a second Monthly Maintenance job starts after the first one ends, at a time no list could hold. The jobs-per-day setting is 1, yet two Monthly Maintenance jobs, two Motorcycle Details or one of each can share a day (decision 0072). And decision 0069 left checking a changed job against the rules for Phase 3.

## Decision

- **A later job is placed by the gap.** On a day that already has a job, the check also offers the placed start after it: the earlier job's end plus the drive between the two addresses, at least the minimum gap, rounded up (decision 0093). A placed start at or after closing time is not offered. The owner may also book a later job at any time after the placed start that falls on the rounding step, such as 12:00 instead of 11:45.
- **A shared day.** A day with a job takes another only when every job on it is a service that can share a day, each within its own maximum. The day then holds up to the jobs-per-day setting or, if higher, the largest maximum among its services: two at launch, so never three.
- **Without both locations** the gap is the minimum gap alone, and the reason says the drive time was not counted.
- **Every owner booking and move is checked.** Booking a job or a series, or changing a job's date, time, address or what it is priced from, runs the check. A broken rule shows a warning naming each rule and each date. A manager can go ahead with a reason, logged with the job as a rule override; anyone else picks another time. Changing only the notes, the vehicle or the crew is not checked.
- **The website books only an open time.** Its booking path has no override.
- **A settings change lists only new breaks.** After a change, each booked job from today on is checked under the rules before and after it, leaving out the notice and the furthest date, which a booked job has passed. A job that breaks a rule it did not break before is listed to keep or reschedule. A listed job moved or canceled is marked as such.
- **Date exceptions replace the unused day closure record.** A Time Off event is kept in its own local copy, filled by the calendar sync in Step 3.

## Alternatives considered

- **Add every quarter hour to the start times.** Would offer the website afternoon starts on empty days, which the owner does not want at launch.
- **Let the jobs-per-day setting cap a shared day.** At 1 it would stop the two Monthly Maintenance jobs the owner wants.
- **Check owner bookings only for a closed day.** The warning would miss a full day or a clash with time off, which the owner asked to see.

## Consequences

The open-times view shows each placed start with the job it follows, so the owner can test the rules. The owner can book any time, as before, but now sees which rule it breaks and leaves a reason.
