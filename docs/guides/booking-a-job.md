---
title: Booking a job
summary: How to read the schedule's five views, book a job or a maintenance series as the price and rules are checked, book outside the rules with a reason, change, cancel or remove a job, and record the final price.
audience: [owner, staff]
visibility: internal
status: current
updated: 2026-11-18
tags: [guides, booking, appointments, schedule, maintenance, control-app]
related: [docs/decisions/0106-add-ons-go-with-listed-services.md, docs/decisions/0107-default-staff-and-needs-you-for-decisions.md, docs/reference/control-app.md, docs/reference/pricing.md, docs/reference/scheduling-and-calendars.md, docs/guides/assigning-staff.md, docs/guides/finding-a-customer.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/decisions/0095-canceling-and-removing-jobs.md, docs/decisions/0096-booking-off-hours-inline-and-calendar-views.md, docs/decisions/0097-rules-alert-before-services-and-schedule-view-bar.md]
---

# Booking a job

The control app opens on **Schedule**. Every price is worked out by the pricing engine from the pricebook; you never type a price, except the final price at the end of a job.

## Read the schedule

A bar of icons along the top of the Schedule screen picks the view, in this order: Schedule, Day, 3 Days, Week and Month. The current view's icon is highlighted; on a computer, hover over an icon to see its name. The bar stays at the top while you scroll, with **Today**, **‹** and **›** beside it. Each phone or computer remembers the last view you picked, so the phone can open in Schedule while the computer opens in Week. With nothing picked yet, the screen opens in Schedule.

- **Schedule:** a list of the days with jobs, opening at today. Scroll down for later days and up for earlier ones; they keep loading as you go. Days with no jobs are left out, but today always shows, with "No jobs today." when it is empty. Each job shows its arrival and leaving time, the customer and the vehicle with its color, the services and total, the address and who is assigned.
- **Day**, **3 Days** and **Week:** an hour on each row and a column for each day. Each job is a block from arrival to leaving time, with the customer, the vehicle and its color, and the services. The hours cover the working day and stretch to fit any job outside it. A closed day is shaded and names why, such as "Sunday is a closed day". Today has a red line at the current time.
- **Month:** a box for each day, with each job as a small block. A day with more than fits shows "+2 more". Tap a day to open it in Day view.

Weeks start on Sunday. Every view has **Today** and **‹** and **›** for the previous and next day, days, week or month; on a phone you can also swipe left or right. Tap a job to open it. A booked job is dark blue; a completed job is light green. A booked job with no one on it says "No staff assigned". Canceled jobs are on none of the views.

## Book a job

1. Tap **Book a job** on the schedule, find the customer (see [finding-a-customer.md](finding-a-customer.md)), and tap **Book a job** on their page.
2. **When and where:** pick the vehicle, the service address, the date and the arrival time. The date starts at the first bookable day. The **Open times** link shows the open start times for the next 90 days. Any date and time can be booked, but one outside the scheduling rules needs a reason (see [Book off hours](#book-off-hours)).
3. **What:** pick the service. The vehicle class and size come from the vehicle; change them if they are wrong. For Full Detail and Interior Only, the condition level appears, with Level 1 picked; change it if the vehicle needs more. Level 3 is priced by hand: type your price before tax for the whole job, add-ons included, and the time on site in steps of 15 minutes, setup and breakdown included. The Level 2 price shows below for reference, and your price is kept as the job's quote. No other service has a condition level. Tick any add-ons: each goes only with some services, and Headlight Restoration is an add-on too (see [Add an add-on outside the rules](#add-an-add-on-outside-the-rules)). Leave the crew as the service's default (one person, or two for Monthly Maintenance) unless you know otherwise.
4. The **Price** box updates as you change anything: each line, the total before tax, the **service time** for the crew and the **time on site** with setup and breakdown. "Full day: consider a second person" appears for 8 or more hours on site for one person. Sales tax is added from Phase 3.
5. Tap **Book**. The job opens with the default staff assigned ("Assigned Kris Grassman, the default staff."), whoever else qualifies. Change the crew on the job if someone else is going, or add the second person to a two-person job, as in [assigning-staff.md](assigning-staff.md). A warning appears if the job overlaps another that day.

## Book off hours

The scheduling rules are checked as soon as you pick the date or time, before you choose the services, and again on every change. Until the services are all chosen, only the rules that don't depend on them are checked: closed days, holidays and Time Off, how far ahead the date is, the allowed arrival times, and whether the day already has a job, so a day with a job shows the alert at once ("a job with no services chosen yet can't share a day"). Once the services are chosen the full check runs and the alert updates: it can appear, such as when the job would run past closing time or doesn't fit before or after another job, or go away, such as for a Monthly Maintenance or Motorcycle Detail that may share the day.

When the choice breaks a rule, such as a closed day, a time not in the day's start times, a full day or a job that would run past closing, an alert appears right under the date and time:

1. First the rule or rules it breaks, in plain words, such as "Sunday is a closed day".
2. Then "Booking off hours is allowed. Give the reason below and it will be logged with the job."
3. Then a **Reason** box. Type why, such as "Customer works weekdays".

Pick a time that fits and the alert and the box go away; nothing is logged. While the alert shows, the reason is required: **Book** brings the form back with "Give the reason for booking off hours." until you type one. The server checks again when you tap **Book**, so if the time was taken while you filled in the form, or the connection was slow, the form comes back with the alert and the box showing.

Only a manager can book off hours. Anyone else sees "Only a manager can book off hours. Pick another time." The website never books off hours.

The job page lists each time the job was booked or moved off hours under **Booked outside the rules**: the rules it broke, the reason, who and when.

## Add an add-on outside the rules

Each add-on goes only with some services ([pricing.md](../reference/pricing.md#which-add-ons-go-with-which-service)): Carpet and Seat Extraction with Full Detail or Interior Only, and Headlight Restoration with Full Detail, Exterior Only or a paint correction. Tick one with another service and the Price box says so, such as "Seat Extraction doesn't go with Exterior Only".

A manager can book it anyway: type why in **Reason for an add-on outside the rules**, such as "Customer's dog got into the back seat", and tap **Book**. Without a reason, **Book** brings the form back with "give the reason for adding it." The reason is logged with the job and listed under **Booked outside the rules** on the job page. Anyone else sees "Pick another, or ask a manager to add it with a reason." Changing such a job later keeps its add-ons without asking again, unless you change its service or add-ons.

## Book a maintenance plan

Monthly and Quarterly Maintenance are booked only here, never on the website.

- **A single visit:** book it like any other job, with **Repeat** left at "A single visit".
- **A repeating series:** set **Repeat** to Monthly or Quarterly and **Visits** to how many, the first included (2 to 24). Monthly visits fall on the same day of each month, Quarterly every three months, at the same time; in a shorter month the visit moves to the last day. Each visit is a job of its own, priced from the pricebook in effect on its date, and the job page shows it is part of a series. Visits more than 90 days ahead are past the furthest bookable date, so the alert lists them by date; give one reason to book the whole series.
- **A second job the same day:** two Monthly Maintenance jobs, two Motorcycle Details or one of each can share a day. **Open times** shows the second job's placed start: the first job's end plus the drive, at least 30 minutes, rounded up to the quarter hour. Book it at that time or later on the quarter hour.

## Change a job

Open the job and tap **Change job**.

- **Date, time, vehicle, address or notes:** change them and tap **Save**. The price stays as booked. A new date, time or address is checked against the scheduling rules, with the same alert and reason box as booking; tap **Save** to save it with the reason. A job listed after a scheduling settings change is marked rescheduled when you move it.
- **What the job is priced from** (service, class, size, condition, add-ons or crew): the Price box shows the new price and says the job will be re-priced. Give a reason, such as "Customer added seat extraction", and tap **Save**. The reason is kept in the job's **Changes** list. Completed and canceled jobs keep their prices; use the final price instead.

## Mark it completed

Under **Status**, tap **Mark completed**, or **Mark booked** to undo it.

## Cancel a job

Only a manager can cancel a job. Open the booked job and tap **Cancel job**. A popup asks what happened:

- **Customer canceled** or **Dixie Detail canceled:** the job is marked canceled at once. It leaves every schedule view, and its time is free again for the website and for you. The job keeps its record: the job page and the customer's page say who canceled, when, who pressed the button, and how much notice was given, such as "2 days, 3 hours' notice". The customer's page lists it under **Canceled jobs**, below the appointments. A canceled job stays canceled; book a new job if it is back on.
- **Created by mistake:** asks once more, "Remove this job for good? This can't be undone." **Remove for good** deletes the job with its lines, staff, flags and change history, as if it never existed. A job booked from a website request sends the request back to the "needs you" list, a quote request with its price, to book again. A job with a payment recorded can't be removed; the message says so, and you can cancel it instead.
- **Keep the job** closes the popup without changing anything.

For a visit of a repeating series, the popup also asks **This visit only** or **This and later visits**; the button you tap applies to that choice. A series with no booked visits left stops repeating.

Jobs canceled before November 7, 2026, and canceled jobs from Baserow, show as "Canceled" with no detail.

## Record the final price

When the job came to a different amount on site, open it and, under **Price**, type the **Final price before tax** and the **reason**, such as "Heavy pet hair" or "One seat left out", then tap **Save final price**. One "On-site adjustment" line is added for the difference, with the reason, so the lines still add up to the total. Typing a new final price replaces that line; typing the lines' own total removes it.
