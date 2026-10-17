---
id: 56
title: "Scheduling rules are settings, checked by one availability check"
summary: "Every scheduling rule becomes a setting seeded from data/booking-rules.yaml; time on site is setup + service time + breakdown; one availability check covers every case."
date: 2026-10-17
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: [docs/decisions/0021-one-job-per-day.md, docs/decisions/0022-second-monthly-job-timing.md]
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md, data/booking-rules.yaml, docs/reference/booking-flow.md, docs/reference/pricing.md, docs/decisions/0021-one-job-per-day.md, docs/decisions/0022-second-monthly-job-timing.md, docs/decisions/0058-service-times-exclude-setup-and-breakdown.md]
---

# 0056: Scheduling rules are settings, checked by one availability check

**Status:** accepted · **Date:** 2026-10-17 · **Area:** scheduling

## Context

Decisions 0021 and 0022 wrote the daily capacity and the timing of a second Monthly Maintenance job as fixed rules, with one hard-coded exception. Any new working pattern, such as afternoon slots or two regular jobs a day, would have needed new code. The scheduling rules also had no place for setup and breakdown, which the crew spends at the customer's address on every job. The owner reviewed the plan on 2026-10-17, before Phase 1 Step 3.

## Decision

- **Every scheduling rule is a setting:** open weekdays, working hours per weekday, date exceptions, start times offered online per weekday, minimum notice, the furthest bookable date, setup and breakdown time, jobs per day, which services can share a day and how many, the gap before a later job, its rounding, the buffer around a timed Time Off event, the Time Off check interval and the stale-copy warning. The launch values are seeded from `data/booking-rules.yaml`; the live values sit in the database and are changed on a control-app settings screen (Phase 3), with change history. The rules of decisions 0021 and 0022 become the launch values of these settings.
- **A settings change applies to bookings made after it.** Booked appointments never move. Booked jobs left outside the new rules are listed for the owner to keep or reschedule. Each appointment stores its start (arrival) time, setup minutes, service minutes, breakdown minutes and crew size as booked.
- **A manager can book outside any rule** in the control app after a warning, with a reason. The website never can.
- **Time on site = setup + service time + breakdown.** Setup and breakdown are 30 minutes each for one person, divided by the number of people. Service time is the one-person service hours from the price matrix, times 0.60 for two people, rounded to the nearest 15 minutes; time on site is also rounded to the nearest 15 minutes. The arrival time the customer picks is when setup starts. The Jobs calendar event covers the whole time on site; the estimate card shows time on site, and "full day" when the one-person time on site is 8 hours or more. Prices don't change.
- **One availability check** covers every case: an open day within the notice and the furthest date, a start time from that day's list, no overlap with a timed Time Off event, room under the jobs-per-day setting with services allowed to share, the gap between jobs, and, when a day holds more than one job, the last one ending by closing time. A single job may run past closing time.
- The quarter-hour rounding of a later job's start stays as proposed in decision 0022, not yet confirmed by the owner.

## Alternatives considered

- **Keep fixed rules with named exceptions.** Every new pattern would need code and a new exception, and the exceptions would multiply.
- **Count setup and breakdown inside the service hours.** That was the old matrix; it hid setup and breakdown from the crew-size calculation, where they divide between two people differently from service time. See decision 0058.

## Consequences

The owner can change working patterns without a developer, within the assumption of one crew working one job at a time; two crews on separate jobs at once would be a later design change. The settings screen, the availability check and the stored per-appointment times are built in Phase 3. Decisions 0021 and 0022 are superseded.
