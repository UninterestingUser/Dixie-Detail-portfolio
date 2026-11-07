---
id: 96
title: "Booking off hours inline, calendar-style schedule views and the customer list"
summary: "The rules are checked as the booking form changes, with a reason box under the date and one Book button; the schedule gets five calendar views; Customers lists everyone, most completed jobs first."
date: 2026-11-07
area: control-app
status: accepted
audience: [owner, staff, developer]
visibility: internal
updated: 2026-11-07
supersedes: []
superseded_by: []
related: [docs/reference/control-app.md, docs/guides/booking-a-job.md, docs/guides/finding-a-customer.md, docs/reference/scheduling-and-calendars.md, docs/decisions/0094-how-the-availability-check-places-and-shares.md, docs/decisions/0046-control-app-django-htmx.md]
---

# 0096: Booking off hours inline, calendar-style schedule views and the customer list

**Status:** accepted · **Date:** 2026-11-07 · **Area:** control-app

## Context

After trying Phase 3, Step 2 the owner asked for changes to the booking form, the schedule and the Customers screen. The rule warning appeared only after **Book** was tapped, with a second button to book outside the rules. The schedule had a day list and a week list. The Customers screen was empty until something was typed.

## Decision

- **The rules alert is inline.** The availability check runs on the booking and change forms as soon as the date or time changes, and again when anything else that affects it changes, such as the services, vehicle or crew. While the choice breaks a rule, an alert right under the date and time names each rule in plain words, such as "Sunday is a closed day", then "Booking off hours is allowed. Give the reason below and it will be logged with the job.", then a reason box. The box is required while the alert shows. A choice that fits removes the alert, and nothing is logged.
- **One Book (or Save) button** does both. The server checks again when the form is sent; if a rule is now broken and no reason was given, such as when the time was taken in the meantime, the form comes back with the alert and the box showing. Only a manager can book off hours.
- **The reason is shown on the job.** Each override records whether the job was booked, moved or had its services changed, and the start it was booked for. The job page lists each one: the rules broken, the reason, who and when. Overrides logged before this change are filled in from the job's change history.
- **Schedule views like the Google Calendar app.** A view icon at the top of the Schedule screen opens a menu: Schedule, Day, 3 Days, Week and Month, replacing the day and week screens. Schedule is a list of the days with jobs that loads more as it scrolls either way, with today shown even when empty. Day, 3 Days and Week have hour rows covering the working day, stretched to fit any job outside it, with each job a block from arrival to leaving. Month is a grid with "+N more" for a full day. Weeks start on Sunday. Closed days are shaded and today has a line at the current time. Swiping left or right moves on a phone.
- **Each device remembers its view** in a cookie, so the phone and the computer can differ. With nothing remembered, the screen opens in Schedule.
- **The Customers screen lists every customer,** those with the most completed jobs first, then the most recent completed visit, then last name, each with their number of completed jobs. The search box is at the top and filters as you type. **Add a customer** is fixed at the bottom of the screen.
- **A new booking opens on the first bookable date,** past the minimum notice and on an open day, so the alert does not show before anything is picked.

## Alternatives considered

- **Keep the separate Book outside the rules button.** Two buttons for one action, and the rule shows only after tapping Book; the owner asked for one button and an alert while picking the time.
- **Remember the view per user on the server.** The owner wants the phone and the computer to differ.
- **Keep the search box at the bottom of the screen on a phone.** With the full list showing, the box belongs above it; the owner asked for it at the top, full width.

## Consequences

The owner sees a rule broken while picking the time, not after. The reason box is the only extra step, and only when needed.
