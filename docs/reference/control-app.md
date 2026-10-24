---
title: Control app
summary: The private web app the owner and staff use to run the business, the screens built so far, the areas still to come, and the rules it follows.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-24
tags: [control-app, back-office, staff]
related: [docs/decisions/0081-monthly-vehicle-data-refresh.md, docs/operations/using-the-catalog-screens.md, docs/decisions/0077-linking-vehicles-to-the-catalog.md, docs/decisions/0079-approval-list.md, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/guides/booking-a-job.md, docs/guides/assigning-staff.md, docs/guides/editing-the-pricebook.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/guides/finding-a-customer.md, docs/guides/installing-the-control-app.md, docs/decisions/0068-control-app-https-static-and-sign-in.md, docs/architecture/network-and-access.md, docs/overview/roadmap.md, docs/decisions/0061-staff-authorized-per-service.md, docs/decisions/0062-arrival-and-departure-by-one-tap.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/reference/scheduling-and-calendars.md]
---

# Control app

The control app is a private web app on the home server, opened in a browser on the Fedora workstations and installed to the Pixel's home screen. It is reached only over the owner's Tailscale network, at `https://server.example-tailnet.ts.net`, and is never exposed to the public internet. Phase 1 built its shell and the screens for customers, the schedule and jobs, staff and the pricebook, and Phase 2 the vehicle catalog's; later phases add the rest of the areas below. How to install it is in [../guides/installing-the-control-app.md](../guides/installing-the-control-app.md).

## What is built

- **The shell.** Every screen shares one layout, designed for the phone first. A bar along the bottom of the phone screen holds **Schedule**, **Customers**, **Staff**, **Pricebook**, **Catalog** and **Account**, six large targets within reach of a thumb; the search box and each form's **Save** and **Cancel** buttons sit just above it. The app opens on today's schedule. On a screen 900 pixels wide or more, the bar moves to the top. The colors are the brand colors in [data/business.yaml](../../data/business.yaml): navy for the top bar, red for the main buttons.
- **Installable.** A web app manifest, home-screen icons (white "DD" on the brand red, drawn by `tools/make_app_icons.py`) and a service worker let Chrome install the app. When the server cannot be reached, such as with Tailscale off, the installed app shows a "Can't reach the control app" page. The service worker keeps nothing else, so no customer data is stored on the device.
- **Sign-in.** Every page needs a signed-in user, except the sign-in page, the health page and the three files that installing needs. Sign-in works over the HTTPS tailnet address with secure cookies; how is in [decision 0068](../decisions/0068-control-app-https-static-and-sign-in.md). **Account** shows who is signed in, links superusers to the Django admin, and signs out.
- **Customers.** Search by name or by phone number in any format, with results as you type (htmx); a customer page with contact details, second contacts, addresses, vehicles, notes and every appointment with its lines, total and payments; and adding and editing customers and vehicles. The steps are in [../guides/finding-a-customer.md](../guides/finding-a-customer.md).
- **Schedule and jobs.** A day list and a week list of jobs; booking a job for a customer and vehicle with the price built live by the pricing engine as the service, add-ons, condition, crew and date change, showing the service time and the time on site; maintenance plans as a single visit or a repeating Monthly or Quarterly series; changing a job, re-pricing it only with a reason; marking it booked, completed or canceled; and the final price with an on-site adjustment and its reason. The owner can book any date; the availability rules arrive in Phase 3. The steps are in [../guides/booking-a-job.md](../guides/booking-a-job.md), and the rules behind them in [decision 0069](../decisions/0069-booking-staffing-and-publishing-in-the-control-app.md).
- **Staff.** The staff page and the service page, with the assign-staff control on each job; see below and [../guides/assigning-staff.md](../guides/assigning-staff.md).
- **Pricebook.** Prices by service and vehicle class laid out like the price matrix, editing a draft, and publishing it with an effective date after deciding each affected booked job; see [pricebook-changes.md](pricebook-changes.md) and [../guides/editing-the-pricebook.md](../guides/editing-the-pricebook.md).
- **Vehicle catalog.** The **Catalog** tab: looking a vehicle up by year, make and model, with its class, size, price basis, each source's facts, how the class was reached, a test price, its overrides and its history; the classification rules in plain words, each change previewed before it applies; the vehicle class settings; the review queue, with one-tap and many-at-once decisions; the differences screen, where each customer's vehicle whose class differs from the catalog's is settled in one tap; and the approval list, where each year range of every model in the job history and the spot-check list is approved or changed. The schedule shows how many model years wait in the queue and, beside it, the last monthly vehicle data refresh: its date, whether it succeeded, and how many models it added and changed and model years it sent to the queue ([decision 0081](../decisions/0081-monthly-vehicle-data-refresh.md)). A customer's vehicle gets its own class on its edit screen. Only a manager changes anything. The steps are in [../operations/using-the-catalog-screens.md](../operations/using-the-catalog-screens.md), and the rules behind them in [decision 0076](../decisions/0076-catalog-screens-in-the-control-app.md), [decision 0077](../decisions/0077-linking-vehicles-to-the-catalog.md) and [decision 0079](../decisions/0079-approval-list.md).
- **Vehicles are named with their color** wherever they are listed or picked, as in "2019 Honda Accord, silver", so a customer's identical vehicles can be told apart ([decision 0067](../decisions/0067-color-tells-identical-vehicles-apart.md)).
- **The Django admin** at `/admin/` opens only for superusers, for fixing data by hand. It lists every business record, with its change history.

## Areas

The areas still to come are described as planned, with the phase that builds each.

| Area | What the owner does or will do there | Phase |
| --- | --- | --- |
| Schedule and jobs | The day and week lists, booking and changing jobs, maintenance series, assigning staff, completing and canceling, and the final price (built in Phase 1); the assign-staff prompt for website bookings and the availability check (Phase 3); "on my way", arrival and departure taps, and marking a job paid (Phase 4) | 1, 3, 4 |
| Customers | Contact details, second contacts, addresses, vehicles, notes, and every appointment and payment (built in Phase 1); texts (Phase 4); resolving quiet-matching flags (Phase 3) | 1, 3, 4 |
| Pricebook | Prices and service times by service and vehicle class, drafts, publishing with an effective date and deciding affected jobs (built in Phase 1); descriptions and photos, and publishing to the website (Phase 3) | 1, 3 |
| Promotions | Percent or dollar discounts, date windows, promo codes and a website banner | 6 |
| Billing | Invoices, payments by method, refunds and receipts | 4 |
| Bookkeeping | The sales journal, processor fees, sales tax owed by period and GnuCash exports | 6 |
| Staff | Which services each person is authorized for, and assigning staff to jobs (built in Phase 1); a screen for adding staff members (the Django admin until then), helpers' pay and what each is owed (Phase 6) | 1, 6 |
| Marketing | Where each customer came from, review-request results, and follow-up campaigns to chosen groups | 6 |
| Messages | Text templates and a log of everything sent and received | 4 |
| Vehicles | Looking vehicles up, the classification rules with a preview before saving, per-model and per-vehicle overrides, each vehicle class's settings, the review queue, the differences screen and the approval list (built in Phase 2); the monthly refresh's report (Phase 2 Step 5) | 2 |
| Settings | The scheduling settings (open days, hours, start times, notice, setup and breakdown, jobs per day and gaps; Phase 3), service area, buffers and user logins | 1 onward |

## Rules the control app follows

- **Linux-first by being a web app.** Nothing to install or update on any workstation. It can be wrapped in its own desktop window later without a rewrite.
- **Changes are traceable.** Every price or description change records who made it and when, and can be undone.
- **Server-rendered pages, phone first.** Screens are Django pages with htmx, designed for the phone first and installable to the home screen; the Django admin is for superusers only. See [decision 0046](../decisions/0046-control-app-django-htmx.md).
- **Everyone signs in.** Each person has their own account, and the sign-in page is reachable only over Tailscale. See [decision 0052](../decisions/0052-django-sign-in-over-tailscale.md).
- **GnuCash stays the books.** The app keeps the sales side and hands GnuCash balanced entries to import.

## Staff authorized per service

One authorization record links each staff member to each service they may perform ([decision 0061](../decisions/0061-staff-authorized-per-service.md)). It covers every active service, add-ons included; history-only services and custom lines are left out.

- **Two screens, one record.** The staff page shows a person's services as switches, and the service page shows a service's staff as switches. Both edit the same record, which saves at each tap and keeps who changed it, so there is nothing to keep in sync.
- **Managers** (staff with the owner role, so only the owner today) are authorized for every service without a record. A new service therefore starts with only managers authorized. Only a manager changes authorizations.

## Assigning staff to a job

- **The assign-staff control.** Each job's page lists every active staff member to assign. Qualified staff are listed first; anyone else appears grayed out, with the services they aren't authorized for. A booked job with no one assigned shows "No staff assigned" on the schedule; the prompt for each new website booking comes in Phase 3.
- **Two-person jobs.** The two people's authorizations together must cover every service on the job; neither needs all of them.
- **Training.** A manager can assign someone not yet authorized after a warning naming the services no one on the crew is authorized for; the reason is recorded on that person's assignment.
- **Crew size.** Assigning a different number of people than the job was booked with (the service's default unless changed) recalculates its service time and time on site (crew time and the setup and breakdown split), and warns if the job now overlaps another that day. The price does not change.
- **Automatic assignment.** When a one-person job is booked and exactly one active staff member is qualified (today, always the owner), the app assigns them and skips the prompt. A two-person job always waits for the crew to be picked. This is a setting, on by default, in [data/booking-rules.yaml](../../data/booking-rules.yaml).
- **Everyone assigned** gets the job and its time-to-leave alert.

## Arrival and departure taps

From Phase 4, a push at the scheduled arrival time will ask "Arrived?", and one tap records it, from the notification or the job screen; "Departed" works the same way, with a reminder at the expected end time. The control app compares actual time on site with the estimate, to show where service times need adjusting. The rules are in [scheduling-and-calendars.md](scheduling-and-calendars.md#arrival-and-departure-times-by-one-tap) and [decision 0062](../decisions/0062-arrival-and-departure-by-one-tap.md).
