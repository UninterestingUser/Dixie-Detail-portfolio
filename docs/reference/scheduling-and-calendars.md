---
title: Scheduling, calendars and time-to-leave alerts
summary: The scheduling settings and the one availability check that decide which days and start times are open, time on site, the calendar sync and conflict rules, time-to-leave alerts and arrival taps.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-11-21
tags: [scheduling, availability, calendar, alerts, settings]
related: [docs/decisions/0112-confirming-bookings-from-new-customers.md, docs/decisions/0098-calendar-sync-queue-and-worker.md, docs/operations/connecting-the-google-calendars.md, docs/decisions/0095-canceling-and-removing-jobs.md, docs/decisions/0096-booking-off-hours-inline-and-calendar-views.md, docs/decisions/0093-quarter-hour-rounding-confirmed.md, docs/decisions/0094-how-the-availability-check-places-and-shares.md, docs/decisions/0091-google-calls-counted-capped-and-cached.md, docs/decisions/0072-motorcycles-class.md, docs/decisions/0065-condition-lengthens-service-time.md, data/booking-rules.yaml, docs/reference/booking-flow.md, docs/reference/pricing.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0057-calendar-sync-and-conflict-rules.md, docs/decisions/0062-arrival-and-departure-by-one-tap.md, docs/decisions/0006-two-google-calendars.md, docs/decisions/0023-time-to-leave-alert.md]
---

# Scheduling, calendars and time-to-leave alerts

These rules are settled policy. The core app owns scheduling; Google Calendar is a mirror and a source of days off, never the source of truth. The launch values are in [data/booking-rules.yaml](../../data/booking-rules.yaml). The settings, the availability check, the manager override, canceling and the open-times view are built (Phase 3, Step 2), and so is the Google Calendar sync (Phase 3, Step 3, [decision 0098](../decisions/0098-calendar-sync-queue-and-worker.md)).

## Every scheduling rule is a setting

Every scheduling rule is a setting, so a new working pattern needs only new setting values, not new code ([decision 0056](../decisions/0056-scheduling-rules-are-settings.md)). The live values sit in the database, seeded from [data/booking-rules.yaml](../../data/booking-rules.yaml) the first time they are read, and are changed on the control app's **Account → Scheduling settings** screen, with change history. Only a manager changes them; everyone signed in can see them. The home base, where drive times start, is on the **Location settings** screen, linked from the scheduling settings.

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
| Services that can share a day | Monthly Maintenance and Motorcycle Detail, each up to 2 a day (decision 0072) |
| Gap before a later job the same day | Drive time between the two addresses, at least 30 minutes |
| Round a later job's start up to | The next 15 minutes (confirmed by the owner on 2026-11-04, [decision 0093](../decisions/0093-quarter-hour-rounding-confirmed.md)) |
| Buffer around a timed Time Off event | 0 minutes |
| Time Off check | Every 5 minutes, and again when a booking is submitted |
| Warning when the last Time Off copy is old | Older than 60 minutes |
| Time-to-leave buffer | 10 minutes before the drive: the Drive to job block and the time-to-leave alert start at the drive time plus this before arrival |
| Unconfirmed bookings per new customer's number | 1: past it, a website booking becomes a request ([decision 0112](../decisions/0112-confirming-bookings-from-new-customers.md)) |
| Unconfirmed bookings from new customers at once | 5: past it, a website booking becomes a request |
| List unconfirmed jobs starting within | 48 hours: the Schedule screen's banner |

**Unconfirmed bookings.** A website booking from a number with no completed job holds its time like any booking, so the availability check counts it, but it is unconfirmed until the customer confirms or a manager marks it confirmed ([booking-flow.md](booking-flow.md#confirming-a-new-customers-booking)). The caps count open unconfirmed bookings: booked, not yet confirmed, starting from now on. A known customer's booking and every booking made in the control app are confirmed and never capped.

## How a scheduling settings change behaves

- **A settings change applies to bookings made after it.** Booked appointments never move. After each save, and after a date exception is added or removed, every booked job from today on is checked under the rules before and after the change. A job that now breaks a rule it did not break before is listed for the owner to keep or reschedule, the same way a pricebook publish lists affected jobs. The notice and the furthest date are not checked, because a booked job has already passed them ([decision 0094](../decisions/0094-how-the-availability-check-places-and-shares.md)).
- **Keep or reschedule.** "Keep as booked" records the choice and changes nothing. "Reschedule" opens the job's change screen; a listed job that is moved or canceled is marked rescheduled or canceled. Jobs still waiting for a choice are counted on the settings screen.
- **Each appointment keeps its times as booked:** its start (arrival) time, setup minutes, service minutes, breakdown minutes and crew size, so a later settings change never alters it.

## The manager override

A manager can book off hours, outside any rule, in the control app by giving a reason. The website never can: its booking path takes only an open time.

- **What is checked.** Booking a job or a repeating series, and changing a job's date, time, address or what it is priced from, run the availability check. Changing only the notes, the vehicle or the crew is not checked.
- **When it is checked.** On the booking and change forms, as soon as the date or time changes, and again when anything else that affects the check changes, such as the services, vehicle or crew ([decision 0096](../decisions/0096-booking-off-hours-inline-and-calendar-views.md)). The server checks again when the form is sent.
- **The alert** appears right under the date and time while the choice breaks a rule. It names each rule broken in plain words, such as "Sunday is a closed day" or "10:15 AM is not a start time on Tuesdays", by date for a series; then says "Booking off hours is allowed. Give the reason below and it will be logged with the job."; then shows a reason box, required while the alert shows. A choice that fits removes the alert and the box, and nothing is logged.
- **Going ahead.** A manager types the reason and taps the one **Book** (or **Save**) button. If the form is sent without a reason while a rule is broken, such as when the time was taken in the meantime, it comes back with the alert and the box. Anyone else is told only a manager can book off hours and to pick another time.
- **The log.** Each override records whether the job was booked, moved or had its services changed, the start it was booked for, the rules broken, the reason, who and when. The job's page lists every one under **Booked off hours**.

## Canceled and removed jobs

A manager cancels a booked job from the **Cancel job** popup on its page ([decision 0095](../decisions/0095-canceling-and-removing-jobs.md)).

- **Customer canceled** or **Dixie Detail canceled** marks the job canceled, with who canceled, who pressed the button and when. Its time is free at once: the availability check, open times, every schedule view and every list of booked jobs leave it out. A canceled job stays canceled.
- **Created by mistake,** after a second confirmation, deletes the job and everything it left: lines, staff assignments, flags, rule overrides, change history, and its quotes when nothing else refers to them. A website request the job was booked from goes back to open, a quote request with its quote, description and photos ([decision 0102](../decisions/0102-removing-or-canceling-a-job-booked-from-a-request.md)). A job with a payment recorded can't be removed this way. Canceling a job booked from a quote request closes the request.
- **A series visit** is canceled or removed alone, or with the series' later booked visits.

## Time on site

**Time on site = setup + service time + breakdown.** It is how long the crew is at the customer's address.

- **Setup and breakdown** are divided by the number of people: 30 + 30 minutes for one person, 15 + 15 for two.
- **Service time** is the one-person service hours from the price matrix, multiplied by 0.60 for two people, rounded to the nearest 15 minutes. Time on site is also rounded to the nearest 15 minutes. How service time is priced is in [pricing.md](pricing.md).
- **The start time the customer picks is the arrival time,** when setup starts. The Jobs calendar event covers the whole time on site. The time-to-leave alert still counts back from the arrival time.
- **The estimate card shows time on site,** not service time, and shows "full day" when the one-person time on site is 8 hours or more.

Examples: one person with 5 hours of service is 6 hours on site, so an 8:00 arrival runs to 14:00. The RAV4 worked example in [pricing.md](pricing.md), at the second condition level, is 7 hours of service and 8 hours on site. Monthly Maintenance with two people runs 2.25 to 4.5 hours on site. A two-person Full Detail on a 2-row Midsize SUV is 3.25 hours of service and 3.75 hours on site at the first condition level, and 4 and 4.5 hours at the third, because condition lengthens the service time.

## The availability check

One availability check covers every case (`scheduling.availability`). A start time is open only when all of these hold:

1. The day is an open weekday, isn't closed by a date exception or an all-day Time Off event, and falls between the minimum notice and the furthest bookable date.
2. The start time is in that day's list of start times.
3. The time on site doesn't overlap a timed Time Off event, plus its buffer (0 minutes at launch).
4. The day has fewer jobs than the jobs-per-day setting, and if it already has a job, both services are allowed to share a day, within each service's per-day maximum.
5. Jobs on the same day are separated by the gap: a later job starts no earlier than the earlier job's end (after breakdown) plus the drive time between the two addresses, at least 30 minutes, rounded up by the rounding setting.
6. When the day holds more than one job, the last one ends by closing time. A single job may run past closing time.

The availability check assumes one crew working one job at a time. Two crews on separate jobs at once would be a later design change.

### What the availability check returns

For each date, the availability check returns the open start times and, for each closed time, the reasons it is closed, each under the name of its rule. A closed day gives the day's reasons instead, such as "Sunday is a closed day" or "Too soon: bookings need 2 days' notice". It reads everything for a range of dates in a few database queries, so it answers 90 days at once.

- **Start times.** A day offers its list of start times. A date exception with different hours offers its own start times, or the weekday's start times that fall within its hours.
- **A placed start.** A day that already has a job also offers the placed start after it: that job's end plus the gap, rounded up. A placed start at or after closing time is not offered. The owner may book a later job at any time after the placed start that falls on the rounding step ([decision 0094](../decisions/0094-how-the-availability-check-places-and-shares.md)).
- **Drive between jobs** comes from the drive times below, leaving at the earlier job's end. Without a location for both addresses, the gap is the minimum gap alone, and the reason says so.
- **A shared day** holds up to the jobs-per-day setting or, if higher, the largest per-day maximum among its services: two at launch.
- **Time Off.** The check reads the local copy of the Time Off calendar, and of any event added to the Jobs calendar by hand, which the calendar sync keeps up to date (see [Calendar sync and conflict rules](#calendar-sync-and-conflict-rules)). Until the calendars are connected the copy is empty and blocks nothing.
- **Canceled jobs** don't count. Requested, booked and completed jobs do.

### Eastern time in every rule

Every scheduling rule is in Eastern time ([decision 0048](../decisions/0048-times-utc-shown-eastern.md)).

- **The notice turns over at midnight Eastern.** At 11:59 PM Eastern on a Monday, two days' notice still makes Wednesday the first bookable date, though it is already Tuesday in UTC.
- **Start times are Eastern clock times.** 8:00 AM is 8:00 AM on both sides of the change to and from daylight saving time.
- **Lengths of time are real minutes.** A two-hour job starting at 12:30 AM on the day daylight saving time ends finishes at 1:30 AM standard time, and the next job's placed start is 2:00 AM.
- **A start time the clocks skip,** such as 2:30 AM on the day daylight saving time starts, is closed with that reason.

## The open-times view

The control app's **Open times** screen, under Account and on the booking form, shows the next 90 days for a job: each open start time, each placed start with the job it follows, and the reasons each closed time is closed. The owner picks a service, vehicle class, size, condition level and crew, and can paste the job's location from Google Maps to count the drive from other jobs that day. The owner uses it to test the settings.

## Open times on the website

The website asks the same availability check through the public API, for a quote's time on site and the customer's address ([public-api.md](public-api.md#open-times-get-open-times)). It shows only the open start times, never why a time is closed, and estimates any drive not already cached instead of asking Google, so browsing never uses the day's Routes calls. A booking checks its time again, with real drive times, under a lock on the day, so two customers can never book the same time ([decision 0100](../decisions/0100-public-api-quotes-and-bookings.md)).

## Daily capacity at launch

At launch each day takes one job, whatever its length. The only jobs that can share a day are Monthly Maintenance and Motorcycle Detail jobs: two Monthly Maintenance, two Motorcycle Detail, or one of each (decision 0072). Example of the gap: an 8:00 Monthly Maintenance job of 3 hours on site followed by a 42-minute drive puts the second job at 11:45.

New patterns need only settings. Afternoon slots: add 13:00 to the start times, set jobs per day to 2 and let the shorter services share a day. Two regular jobs a day: set jobs per day to 2 and let every service share a day.

The 30-minute minimum gap is the owner's rule. Rounding a later job's start up to the next quarter hour was confirmed by the owner on 2026-11-04 ([decision 0093](../decisions/0093-quarter-hour-rounding-confirmed.md)).

## Maintenance plans are booked by the owner

Monthly and Quarterly Maintenance never appear on the website. The owner books them in the control app, as a single visit or a repeating series ([../guides/booking-a-job.md](../guides/booking-a-job.md)).

- **A Monthly series** repeats on the same day of each month and **a Quarterly series** every three months, at the same arrival time. In a month too short for that day, the visit falls on the month's last day.
- **Each visit is its own job,** priced from the pricebook in effect on its own date, with its own quote, so a series can span a price change. A series has 2 to 24 visits.
- **Each visit is checked against the scheduling rules.** A visit outside them, such as one more than 90 days ahead, is listed by date in the alert, and a manager books the series with one reason, logged with each visit outside the rules. The control app also warns when a job overlaps another that day.

## The two Google Workspace calendars

| Calendar | Who writes to it | What it holds |
| --- | --- | --- |
| Dixie Detail Jobs | The system only | One event per appointment, covering the whole time on site. The title carries the service and vehicle, the location is the job address for one-tap directions, and the notes hold the customer's phone, services, total and payment method. A "Drive to job" block precedes it |
| Dixie Detail Time Off | The owner | Days off, holidays, appointments and anything else that should block time. An all-day event closes that day; a timed event blocks only its own time |

Both calendars exist under the owner's Workspace account, set to Eastern time (created 2026-10-11).

## Calendar sync and conflict rules

The database is the only record of appointments ([decision 0057](../decisions/0057-calendar-sync-and-conflict-rules.md)). The app writes the Jobs calendar and reads the Time Off calendar; neither calendar ever changes an appointment. The sync is built (Phase 3, Step 3); how it works is in [decision 0098](../decisions/0098-calendar-sync-queue-and-worker.md), and how to connect it in [../operations/connecting-the-google-calendars.md](../operations/connecting-the-google-calendars.md).

### How the sync runs

- **A queue in the database.** Booking, moving, changing, canceling or removing a job, and closing or reopening a date, add a task in the same database transaction, so a booking never waits for Google and no change is lost.
- **The calendar worker,** a container of its own in the stack, pushes each task within seconds. While Google is down it tries again after 30 seconds, then waits twice as long each time, up to 15 minutes. It survives restarts, because the queue is in the database.
- **Every Time Off check** (5 minutes at launch) the worker copies the Time Off calendar, flags clashes and checks the Jobs calendar for edits made in Google.
- **Every night at 3:35 AM** `dixie-calendar-check.timer` runs the full check, `python manage.py sync_calendars`, which compares every appointment and closed date from today on with the Jobs calendar and repairs any difference. It reports to Healthchecks ([../operations/monitoring.md](../operations/monitoring.md)).
- **The first run.** `python manage.py sync_calendars --dry-run` prints every event the Jobs calendar should hold, changing nothing; `python manage.py sync_calendars` then creates them.
- **Past jobs are left alone.** The check covers today on; a job's event stays on the calendar after the day.

### Access to the calendars

- The core app connects through a Google service account that both calendars are shared with: edit rights on Jobs, read rights on Time Off. Nothing else in the Workspace is visible to it.
- Customers are never added as event guests; they get texts instead, and guests would make Google email them.
- When a helper joins, Jobs is shared with them as view-only.

### Jobs calendar: the app writes, the owner reads

1. Each booked or completed appointment has one event and one "Drive to job" block, linked to it by an ID stored on the appointment (its calendar key) and in the events' private extended properties. The event IDs are made from the key.
   - **The job event** covers the whole time on site. Its title is the service and the vehicle, such as "Full Detail · 2019 Toyota RAV4, blue"; its location is the job address; its notes hold the customer's name and phone, the services, the total and the payment method. A job imported without its times shows as an hour.
   - **An unconfirmed job's event** uses Google's yellow event color, Banana (color 5), and its notes add "Not confirmed yet: call to confirm." or "… waiting for a text reply." Once the job is confirmed the event has no color of its own, so it shows in the calendar's color again ([decision 0112](../decisions/0112-confirming-bookings-from-new-customers.md)).
   - **The Drive to job block** runs from the leave time to the arrival time, with a notification at the leave time. The leave time is the drive time from the home base plus the time-to-leave buffer (10 minutes at launch) before arrival. A job with no drive time recorded, such as one with no address location, has no block.
   - A canceled or removed job's events are deleted, so the Jobs calendar never shows canceled jobs.
   - A test record, such as the smoke test's booking, never goes on the Jobs calendar ([public-api.md](public-api.md#test-records)).
2. Booking, moving or canceling an appointment updates its events within a minute. If Google is down, the change waits in a queue and retries; a booking never waits for Google.
3. Appointments change in the control app, not in Google. A Jobs event edited in Google, its color included, is restored to the app's version at the next check, within 5 minutes, and the control app notes the reset on its home screen and on the job. A Jobs event deleted in Google is recreated and noted the same way.
4. An event added to Jobs by hand counts as busy time and is flagged on the control app's home screen, so the owner can move it to Time Off or delete it. The app never deletes it; the flag goes away when the event does.
5. Days closed in the control app show on Jobs as all-day "Closed" events.
6. A full check every night compares future appointments with the Jobs events and repairs any difference: missing events are created, edited ones put back, and app events for jobs no longer booked deleted.

### Time Off calendar: the owner writes, the app reads

1. An all-day event closes every day it covers.
2. A timed event blocks only its own time, plus the buffer setting (0 minutes at launch). A job that fits before or after it can still be booked.
3. Every event counts, repeating events included. The Free/Busy setting is ignored, because Google marks all-day events "Free" by default.
4. Deleting an event reopens its time at the next check.
5. The app checks Time Off every 5 minutes and again when a booking is submitted.
6. Time off added over a booked appointment never cancels or moves it. The control app flags the clash on its home screen, with **Keep**, **Reschedule** and **Cancel**; only a manager keeps or cancels. A kept clash stays kept. A clash that goes away, because the job or the time off moved, clears itself. The push alert to the owner comes with push notifications in Phase 4.

### When Google is unreachable

- Booking keeps working, because the database is the source of truth. Jobs changes queue and catch up later; availability uses the last copy of Time Off.
- If that copy is more than 60 minutes old, the control app shows a warning on the home screen and the booking form, with Google's last error. Until the calendars are connected, the same place says so.

## Time-to-leave alerts

Each job sends a push alert when it is time to leave: the drive time plus 10 minutes before the arrival time. A 32-minute drive produces the alert 42 minutes before the arrival time.

- **Drive time** is measured from the home base to the job address with predicted traffic for that time of day. For a later job the same day, it is measured from the earlier job's address.
- **Kept fresh.** It is worked out at booking and again on the morning of the job.
- **Delivery.** A normal push notification from the control app installed on the Pixel, sent to every staff member assigned to the job.
- **Contents.** The customer's name, the address as a one-tap navigation link, and an "On my way" button that texts the customer.
- **Backup.** A "Drive to job" block on the Jobs calendar from the leave time to the arrival time, with a calendar notification.
- **Settings.** The 10-minute buffer (the time-to-leave buffer on the scheduling settings screen), the home base and each staff member's starting point are settings.

## Drive times

Built in Phase 3, Step 1 ([decision 0091](../decisions/0091-google-calls-counted-capped-and-cached.md)). The alert, the "Drive to job" block and the gap between jobs use them as those are built.

- **From Google's Routes API,** with traffic predicted for the time of day. A drive from the home base counts back from the arrival time: traffic is predicted for the departure.
- **Cached** by the two addresses and the hour of the day, Eastern, for 30 days, so a search over many start times asks Google once per pair and hour.
- **When Google can't be reached,** or the day's cap on Routes calls is reached, the drive time is estimated from the straight-line distance times 1.3, at 40 mph, and marked "Estimated" wherever it is shown. An estimate is not cached.
- **The home base** is a database setting on the control app's **Account → Location settings** screen, checked with the Census geocoder. It is the owner's home, so it is never written to the repository or the docs. The road factor, speed, cache time and Google's daily caps are on the same screen.
- **At booking,** each job records its drive from the home base, in minutes, and whether it was estimated. Changing the job's address or start works it out again.

Drive times come from Google Maps Platform, inside its free monthly allowance; each call is counted, and the month's counts are on the Location settings screen.

## Arrival and departure times by one tap

Each appointment will record when the crew arrived and departed ([decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md)). This is built in Phase 4, with the time-to-leave alert and "On my way".

- **Arrived.** A push at the scheduled arrival time asks "Arrived?", and one tap records it, from the notification or the job screen. A tap on the job screen also takes a single location reading to confirm the address.
- **Departed** works the same way, with a reminder at the expected end time.
- **No background location.** The control app is a web app, and a web app cannot use location in the background.
- **What is stored.** Each appointment stores its arrival and departure times and how each was recorded: tap, automatic or edited. Corrections are logged.
- **Staff.** With staff, times are recorded only at job addresses during their assigned jobs, with their agreement.
- **Why it is recorded.** The control app compares actual time on site with the estimate, to show where service times need adjusting.

Automatic arrival and departure is a later add-on, not scheduled: a small native Android companion app using Android geofencing. It is described in [decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md) and listed in the [roadmap](../overview/roadmap.md).
