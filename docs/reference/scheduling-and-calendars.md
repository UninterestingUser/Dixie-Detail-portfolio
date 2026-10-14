---
title: Scheduling, calendars and time-to-leave alerts
summary: The booking rules that decide which days and times are open, how the two Google Workspace calendars are used, and how time-to-leave alerts are timed and delivered.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [scheduling, availability, calendar, alerts]
related: [data/booking-rules.yaml, docs/reference/booking-flow.md, docs/decisions/0021-one-job-per-day.md, docs/decisions/0022-second-monthly-job-timing.md, docs/decisions/0006-two-google-calendars.md]
---

# Scheduling, calendars and time-to-leave alerts

These rules are settled policy. The core app owns scheduling from Phase 3; Google Calendar is a mirror and a source of days off, never the source of truth. The numbers are in [data/booking-rules.yaml](../../data/booking-rules.yaml).

## Which days and times are open

- **Working days.** Closed Sundays by default. Holidays and days off are set in the control app or on the Time Off calendar.
- **Notice.** No same-day or next-day booking; the earliest bookable day is two days out.
- **Arrival times.** 8:00, 8:30 or 9:00 AM, the same for every service.
- **Capacity.** One job per day. Every service, Quarterly Maintenance included, takes the whole day whatever its length, with one exception below.
- **Job length.** The matrix hours, scaled for crew size and rounded to 15 minutes, set the calendar event's length and the estimate card's time.

## Two Monthly Maintenance jobs can share a day

The only exception to one job per day: two Monthly Maintenance jobs on the same day. The second starts when the first is due to finish, plus a buffer equal to the drive time between the two addresses, with a 30-minute minimum. The start is rounded up to the next quarter hour. Example: an 8:00 job of 3 hours followed by a 42-minute drive puts the second at 11:45.

The 30-minute minimum is the owner's rule. The rounding up to the quarter hour was proposed during planning and is not yet confirmed by the owner.

## Maintenance plans are booked by the owner

Monthly and Quarterly Maintenance never appear on the website. The owner books them in the control app, as a single visit or a repeating series.

## The two Google Workspace calendars

| Calendar | Who writes to it | What it holds |
| --- | --- | --- |
| Dixie Detail Jobs | The system only | One event per appointment. The title carries the service and vehicle, the location is the job address for one-tap directions, and the notes hold the customer's phone, services, total and payment method. A "Drive to job" block precedes it |
| Dixie Detail Time Off | The owner | Days off, holidays and anything else that should close a day. An all-day event closes that day on the website |

Both calendars exist under the owner's Workspace account, set to Eastern time (created 2026-10-11).

How the calendars are used:

1. The core app connects through a Google service account that both calendars are shared with: edit rights on Jobs, read rights on Time Off. Nothing else in the Workspace is visible to it.
2. Customers are never added as event guests; they get texts instead, and guests would make Google email them.
3. Appointments change in the control app, not in Google. An edit made to a Jobs event in Google is overwritten at the next sync.
4. When a helper joins, Jobs is shared with them as view-only.
5. Booking keeps working if Google is unreachable, because the database is the source of truth.

## Time-to-leave alerts

Each job sends a push alert when it is time to leave: the drive time plus 10 minutes before the scheduled start. A 32-minute drive produces the alert 42 minutes before the start.

- **Drive time** is measured from the home base to the job address with predicted traffic for that time of day. For the second Monthly Maintenance job of a day, it is measured from the first job's address.
- **Kept fresh.** It is worked out at booking and again on the morning of the job.
- **Delivery.** A normal push notification from the control app installed on the Pixel, sent to every staff member assigned to the job.
- **Contents.** The customer's name, the address as a one-tap navigation link, and an "On my way" button that texts the customer.
- **Backup.** A "Drive to job" block on the Jobs calendar from the leave time to the start, with a calendar notification.
- **Settings.** The 10-minute buffer, the home base and each staff member's starting point are settings.

Drive times come from Google Maps Platform, inside its free monthly allowance.
