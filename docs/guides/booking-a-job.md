---
title: Booking a job
summary: How to book a job or a repeating maintenance series in the control app with the price worked out as you go, change or cancel it, mark it completed, and record the final price with an on-site adjustment.
audience: [owner, staff]
visibility: internal
status: current
updated: 2026-10-18
tags: [guides, booking, appointments, schedule, maintenance, control-app]
related: [docs/reference/control-app.md, docs/reference/pricing.md, docs/reference/scheduling-and-calendars.md, docs/guides/assigning-staff.md, docs/guides/finding-a-customer.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md]
---

# Booking a job

The control app opens on **Schedule**, today's jobs. Every price is worked out by the pricing engine from the pricebook; you never type a price, except the final price at the end of a job.

## See the day or the week

- **Schedule** shows one day: each job's arrival and leaving time, the customer and vehicle with its color, the services and total, the address, and who is assigned. A booked job with no one on it says "No staff assigned".
- Tap **‹** and **›** for the day before and after, **Today** to come back, and **Week** for Monday to Sunday at a glance. Tap a day's heading in the week to open that day.
- Tap a job to open it.

## Book a job

1. Tap **Book a job** on the schedule, find the customer (see [finding-a-customer.md](finding-a-customer.md)), and tap **Book a job** on their page.
2. **When and where:** pick the vehicle, the service address, the date and the arrival time. Any date can be booked; the availability rules arrive in Phase 3.
3. **What:** pick the service. The vehicle class and size come from the vehicle; change them if they are wrong. Pick the condition level for Full Detail, Interior Only and Exterior Only. Tick any add-ons. Leave the crew as the service's default (one person, or two for Monthly Maintenance) unless you know otherwise.
4. The **Price** box updates as you change anything: each line, the total before tax, the **service time** for the crew and the **time on site** with setup and breakdown. "Full day: consider a second person" appears for 8 or more hours on site for one person. Sales tax is added from Phase 3.
5. Tap **Book**. The job opens. When only one active staff member is qualified for a one-person job (today, you), they are assigned at once; otherwise assign staff as in [assigning-staff.md](assigning-staff.md). A warning appears if the job overlaps another that day.

## Book a maintenance plan

Monthly and Quarterly Maintenance are booked only here, never on the website.

- **A single visit:** book it like any other job, with **Repeat** left at "A single visit".
- **A repeating series:** set **Repeat** to Monthly or Quarterly and **Visits** to how many, the first included (2 to 24). Monthly visits fall on the same day of each month, Quarterly every three months, at the same time; in a shorter month the visit moves to the last day. Each visit is a job of its own, priced from the pricebook in effect on its date, and the job page shows it is part of a series.

## Change a job

Open the job and tap **Change job**.

- **Date, time, vehicle, address or notes:** change them and tap **Save**. The price stays as booked.
- **What the job is priced from** (service, class, size, condition, add-ons or crew): the Price box shows the new price and says the job will be re-priced. Give a reason, such as "Customer added seat extraction", and tap **Save**. The reason is kept in the job's **Changes** list. Completed and canceled jobs keep their prices; use the final price instead.

## Mark it completed or canceled

Under **Status**, tap **Mark completed**, **Cancel job** or **Mark booked** to undo either. A canceled job stays on the schedule, faded.

## Record the final price

When the job came to a different amount on site, open it and, under **Price**, type the **Final price before tax** and the **reason**, such as "Heavy pet hair" or "One seat left out", then tap **Save final price**. One "On-site adjustment" line is added for the difference, with the reason, so the lines still add up to the total. Typing a new final price replaces that line; typing the lines' own total removes it.
