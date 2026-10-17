---
title: Scheduling, calendars and time-to-leave alerts
summary: The scheduling settings and the one availability check that decide which days and start times are open, time on site, the calendar sync and conflict rules, time-to-leave alerts and arrival taps.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-17
tags: [scheduling, availability, calendar, alerts, settings]
related: [data/booking-rules.yaml, docs/reference/booking-flow.md, docs/reference/pricing.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0057-calendar-sync-and-conflict-rules.md, docs/decisions/0062-arrival-and-departure-by-one-tap.md, docs/decisions/0006-two-google-calendars.md, docs/decisions/0023-time-to-leave-alert.md]
---

# Scheduling, calendars and time-to-leave alerts

These rules are settled policy. The core app owns scheduling from Phase 3; Google Calendar is a mirror and a source of days off, never the source of truth. The launch values are in [data/booking-rules.yaml](../../data/booking-rules.yaml).

## Every scheduling rule is a setting

Every scheduling rule is a setting, so a new working pattern needs only new setting values, not new code ([decision 0056](../decisions/0056-scheduling-rules-are-settings.md)). The launch values are seeded from [data/booking-rules.yaml](../../data/booking-rules.yaml). From Phase 3 the live values will sit in the database and be changed on the control app's settings screen, with change history.

| Setting | Launch value |
| --- | --- |
| Open weekdays | Monday to Saturday (Sunday closed) |
| Working hours, per open weekday | 08:00 to 18:00 |
| Date exceptions | A date closed, or with different hours, set in the control app or by a Time Off event |
| Start times offered online, per weekday | 08:00, 08:30 and 09:00 on every open day |
| Minimum notice | 2 days (no same-day or next-day booking) |
| Furthest date bookable online | 90 days ahead |
| Setup time before each job | 30 minutes for one person, divided by the number of people on the job |
| Breakdown time after each job | 30 minutes for one person, divided by the number of people on the job |
| Jobs per day | 1 |
| Services that can share a day | Monthly Maintenance, up to 2 a day |
| Gap before a later job the same day | Drive time between the two addresses, at least 30 minutes |
| Round a later job's start up to | 15 minutes (proposed in decision 0022; the owner has not confirmed it yet) |
| Buffer around a timed Time Off event | 0 minutes |
| Time Off check | Every 5 minutes, and again when a booking is submitted |
| Warning when the last Time Off copy is old | Older than 60 minutes |

## How a scheduling settings change behaves

- **A settings change applies to bookings made after it.** Booked appointments never move. When a change leaves booked jobs outside the new rules, the settings screen will list them for the owner to keep or reschedule, the same way a pricebook publish lists affected jobs.
- **Each appointment keeps its times as booked:** its start (arrival) time, setup minutes, service minutes, breakdown minutes and crew size, so a later settings change never alters it.
- **A manager can book outside any rule** in the control app (a closed day, a Time Off block, a full day) after a warning, with a reason. The website never can.

## Time on site

**Time on site = setup + service time + breakdown.** It is how long the crew is at the customer's address.

- **Setup and breakdown** are divided by the number of people: 30 + 30 minutes for one person, 15 + 15 for two.
- **Service time** is the one-person service hours from the price matrix, multiplied by 0.60 for two people, rounded to the nearest 15 minutes. Time on site is also rounded to the nearest 15 minutes. How service time is priced is in [pricing.md](pricing.md).
- **The start time the customer picks is the arrival time,** when setup starts. The Jobs calendar event covers the whole time on site. The time-to-leave alert still counts back from the arrival time.
- **The estimate card shows time on site,** not service time, and shows "full day" when the one-person time on site is 8 hours or more.

Examples: one person with 5 hours of service is 6 hours on site, so an 8:00 arrival runs to 14:00. The RAV4 worked example in [pricing.md](pricing.md) is 6.5 hours of service and 7.5 hours on site. Monthly Maintenance with two people runs 2.25 to 4.5 hours on site. A two-person Full Detail on a 2-row Midsize SUV is 3.25 hours of service and 3.75 hours on site.

## The availability check

One availability check covers every case. From Phase 3, a start time will be offered online only when all of these hold:

1. The day is an open weekday, isn't closed by a date exception or an all-day Time Off event, and falls between the minimum notice and the furthest bookable date.
2. The start time is in that day's list of start times.
3. The time on site doesn't overlap a timed Time Off event, plus its buffer (0 minutes at launch).
4. The day has fewer jobs than the jobs-per-day setting, and if it already has a job, both services are allowed to share a day, within each service's per-day maximum.
5. Jobs on the same day are separated by the gap: a later job starts no earlier than the earlier job's end (after breakdown) plus the drive time between the two addresses, at least 30 minutes, rounded up by the rounding setting.
6. When the day holds more than one job, the last one ends by closing time. A single job may run past closing time.

The availability check assumes one crew working one job at a time. Two crews on separate jobs at once would be a later design change.

## Daily capacity at launch

At launch each day takes one job, whatever its length. The only jobs that can share a day are two Monthly Maintenance jobs. Example of the gap: an 8:00 Monthly Maintenance job of 3 hours on site followed by a 42-minute drive puts the second job at 11:45.

New patterns need only settings. Afternoon slots: add 13:00 to the start times, set jobs per day to 2 and let the shorter services share a day. Two regular jobs a day: set jobs per day to 2 and let every service share a day.

The 30-minute minimum gap is the owner's rule. Rounding a later job's start up to the quarter hour was proposed during planning and is not yet confirmed by the owner.

## Maintenance plans are booked by the owner

Monthly and Quarterly Maintenance never appear on the website. The owner books them in the control app, as a single visit or a repeating series.

## The two Google Workspace calendars

| Calendar | Who writes to it | What it holds |
| --- | --- | --- |
| Dixie Detail Jobs | The system only | One event per appointment, covering the whole time on site. The title carries the service and vehicle, the location is the job address for one-tap directions, and the notes hold the customer's phone, services, total and payment method. A "Drive to job" block precedes it |
| Dixie Detail Time Off | The owner | Days off, holidays, appointments and anything else that should block time. An all-day event closes that day; a timed event blocks only its own time |

Both calendars exist under the owner's Workspace account, set to Eastern time (created 2026-10-11).

## Calendar sync and conflict rules

The database is the only record of appointments ([decision 0057](../decisions/0057-calendar-sync-and-conflict-rules.md)). The app writes the Jobs calendar and reads the Time Off calendar; neither calendar ever changes an appointment. The sync is built in Phase 3.

### Access to the calendars

- The core app connects through a Google service account that both calendars are shared with: edit rights on Jobs, read rights on Time Off. Nothing else in the Workspace is visible to it.
- Customers are never added as event guests; they get texts instead, and guests would make Google email them.
- When a helper joins, Jobs is shared with them as view-only.

### Jobs calendar: the app writes, the owner reads

1. Each appointment has one event and one "Drive to job" block, linked to it by an ID stored on the appointment and in the event's private extended properties.
2. Booking, moving or cancelling an appointment updates its events within a minute. If Google is down, the change waits in a queue and retries; a booking never waits for Google.
3. Appointments change in the control app, not in Google. A Jobs event edited in Google is restored to the app's version at the next sync, and the control app notes the reset. A Jobs event deleted in Google is recreated.
4. An event added to Jobs by hand counts as busy time and is flagged in the control app, so the owner can move it to Time Off or delete it. The app never deletes it.
5. Days closed in the control app show on Jobs as all-day "Closed" events.
6. A full check every night compares future appointments with the Jobs events and repairs any difference.

### Time Off calendar: the owner writes, the app reads

1. An all-day event closes every day it covers.
2. A timed event blocks only its own time, plus the buffer setting (0 minutes at launch). A job that fits before or after it can still be booked.
3. Every event counts, repeating events included. The Free/Busy setting is ignored, because Google marks all-day events "Free" by default.
4. Deleting an event reopens its time at the next check.
5. The app checks Time Off every 5 minutes and again when a booking is submitted.
6. Time off added over a booked appointment never cancels or moves it. The control app flags the clash and sends the owner a push alert to keep, reschedule or cancel the job.

### When Google is unreachable

- Booking keeps working, because the database is the source of truth. Jobs changes queue and catch up later; availability uses the last copy of Time Off.
- If that copy is more than 60 minutes old, the control app shows a warning.

## Time-to-leave alerts

Each job sends a push alert when it is time to leave: the drive time plus 10 minutes before the arrival time. A 32-minute drive produces the alert 42 minutes before the arrival time.

- **Drive time** is measured from the home base to the job address with predicted traffic for that time of day. For a later job the same day, it is measured from the earlier job's address.
- **Kept fresh.** It is worked out at booking and again on the morning of the job.
- **Delivery.** A normal push notification from the control app installed on the Pixel, sent to every staff member assigned to the job.
- **Contents.** The customer's name, the address as a one-tap navigation link, and an "On my way" button that texts the customer.
- **Backup.** A "Drive to job" block on the Jobs calendar from the leave time to the arrival time, with a calendar notification.
- **Settings.** The 10-minute buffer, the home base and each staff member's starting point are settings.

Drive times come from Google Maps Platform, inside its free monthly allowance.

## Arrival and departure times by one tap

Each appointment will record when the crew arrived and departed ([decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md)). This is built in Phase 4, with the time-to-leave alert and "On my way".

- **Arrived.** A push at the scheduled arrival time asks "Arrived?", and one tap records it, from the notification or the job screen. A tap on the job screen also takes a single location reading to confirm the address.
- **Departed** works the same way, with a reminder at the expected end time.
- **No background location.** The control app is a web app, and a web app cannot use location in the background.
- **What is stored.** Each appointment stores its arrival and departure times and how each was recorded: tap, automatic or edited. Corrections are logged.
- **Staff.** With staff, times are recorded only at job addresses during their assigned jobs, with their agreement.
- **Why it is recorded.** The control app compares actual time on site with the estimate, to show where service times need adjusting.

Automatic arrival and departure is a later add-on, not scheduled: a small native Android companion app using Android geofencing. It is described in [decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md) and listed in the [roadmap](../overview/roadmap.md).
