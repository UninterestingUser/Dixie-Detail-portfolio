---
id: 97
title: "The rules alert before the services are chosen, and the schedule's view bar"
summary: "The booking form checks the rules the date and time break on their own before any service is picked; the schedule's view menu becomes a bar of icons kept along the top of the screen."
date: 2026-11-07
area: control-app
status: accepted
audience: [owner, staff, developer]
visibility: internal
updated: 2026-11-07
supersedes: []
superseded_by: []
related: [docs/decisions/0096-booking-off-hours-inline-and-calendar-views.md, docs/decisions/0094-how-the-availability-check-places-and-shares.md, docs/reference/control-app.md, docs/guides/booking-a-job.md, docs/reference/scheduling-and-calendars.md]
---

# 0097: The rules alert before the services are chosen, and the schedule's view bar

**Status:** accepted · **Date:** 2026-11-07 · **Area:** control-app

## Context

After trying the follow-up in [decision 0096](0096-booking-off-hours-inline-and-calendar-views.md), the owner found two problems.

- The alert under the date and time appeared only once the services were chosen, because the check needs a priced job. Picking a closed day first showed nothing.
- On the owner's phone the Schedule screen showed only the Schedule list, with no way to change the view. The view menu sat at the top of the page, above the list. The list loads earlier days as soon as the top of it is in view, and keeps the days in view where they were, so on opening it loaded earlier days above and pushed the menu out of sight; scrolling up loaded more past days each time, so the menu was never reached.

## Decision

- **The alert appears as soon as the date or time is picked.** Until the services are all chosen, the booking and change forms check every rule that can be judged without them: closed days, date exceptions and Time Off, the minimum notice and the furthest bookable date, the allowed arrival times, and sharing the day. For sharing the day the new job is taken as a regular one that can't share, so a day that already has a job shows the alert at once, naming "a job with no services chosen yet".
- **Once the services are chosen the full check runs** and updates the alert: it can appear (the job runs past closing time, or doesn't fit before or after another job) or go away (a Monthly Maintenance or Motorcycle Detail that may share the day). The form is checked again on every change, as before, and the server checks the full rules when the form is sent.
- **A bar of icons replaces the view menu,** one per view in this order: Schedule, Day, 3 Days, Week and Month. The current view's icon is highlighted; each icon has a label for screen readers and a tooltip on a computer. The bar and the **Today**, **‹** and **›** buttons sit in one row just below the top bar and stay there while the page scrolls.
- **The icons are Google's Material Symbols** (Outlined), the set Google's own apps draw from, closest to the Google Calendar app's: view_agenda, calendar_view_day, view_column, calendar_view_week and calendar_view_month. They are open source under the Apache License 2.0 and served by the app itself from one SVG file with the license beside it, not from a CDN, so they work offline in the installed app.

## Alternatives considered

- **Wait for the services, as before.** The owner picks the date first; a closed day should show at once.
- **Judge the gap and closing time with a guessed length.** A guess could show an alert that goes away, or hide one that should show; those rules wait for the services.
- **Stop loading earlier days on opening.** The menu would still scroll away with the list. A bar that stays at the top is always in reach, as in the Google Calendar app.
- **Load the icons from Google's font CDN.** It would not work offline in the installed app, and would call Google from a private app.

## Consequences

The alert shows while the owner picks the date and time, and may change once the services are chosen. The view can be changed from anywhere on the Schedule screen.
