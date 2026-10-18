---
title: Finding a customer and their history
summary: How to find a customer in the control app by name or by phone number in any format, what the customer page shows, and how to add or edit a customer or a vehicle.
audience: [owner, staff]
visibility: internal
status: current
updated: 2026-10-18
tags: [guides, customers, vehicles, search, control-app]
related: [docs/reference/control-app.md, docs/guides/installing-the-control-app.md, docs/reference/returning-customers.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md]
---

# Finding a customer and their history

The **Customers** screen finds any customer. From there you can see everything about them on one page, add or change their details and vehicles, and book them a job. You need to be signed in; see [installing-the-control-app.md](installing-the-control-app.md).

## Find a customer

1. Tap **Customers** in the bar at the bottom of the screen. On a computer the bar is at the top.
2. Type in the search box. On a phone it sits just above the bottom bar, where your thumb reaches. Results appear as you type.
3. Tap the customer.

What you can type:

- **A name, or part of one.** "pat", "Pat Example" and "example pat" all find Pat Example. Every word you type must match the first name, last name, company or a second contact's name, so adding a word narrows the list.
- **A phone number in any format.** "(423) 555-0142", "423-555-0142", "423.555.0142", "4235550142" and "+1 423 555 0142" all work.
- **Part of a phone number,** at least three digits, such as the last four: "0142".
- **A name and part of a number,** such as "Pat 0142".

A second contact's number or name finds the customer they belong to. Each result shows the customer's number, their vehicles with each vehicle's color, and any second contacts, so you can pick the right person when two names are alike. When nothing matches, the screen offers **Add a new customer**. From a customer's page, **Book a job** books a job for them; see [booking-a-job.md](booking-a-job.md), and tap an appointment's date to open the job.

## What the customer page shows

From the top:

- **Contact:** the mobile number (tap it to call, or tap **Text**), email, where the customer came from, and when they became a customer. Imported customers say "imported from Baserow".
- **Notes** about the customer.
- **Second contacts,** such as a spouse, with their own numbers.
- **Addresses,** marked "No longer used", "Out of area, approved" or "Not verified" where that applies.
- **Vehicles,** each shown as year, make, model and color, such as "2019 Honda Accord, silver", with its vehicle class and size. The color tells a customer's identical vehicles apart. Missing details are listed as "To fill in"; fill them in at the next visit.
- **Appointments,** newest first: the date and time in Eastern time, the status, the vehicle and address, every priced line and the total before tax, and each payment with its method, tip and date. A completed job says "Paid in full", "Balance" with the amount still owed, or "Not paid". A no-charge job shows its no-charge line and a total of $0.00.

## Add or edit a customer

- **New customer:** on the Customers screen, tap **Add a customer**. Only the first name is required. Type the mobile number in any format; it is saved as 10 digits. A number that is not a full 10-digit US number is refused with a message.
- **Edit:** on the customer page, tap **Edit customer**, change what you need, and tap **Save**. **Save** and **Cancel** stay at the bottom of the screen while you scroll.

Every change records who made it and when.

## Add or edit a vehicle

1. On the customer page, tap **Add a vehicle**, or **Edit** on a vehicle.
2. Fill in the year, make, model and color. Always add the color when a customer has two vehicles of the same make, model and year.
3. Pick the vehicle class and, if the class has sizes, the size variant. A size variant must belong to the class you picked; leave both blank if you are not sure.
4. Tap **Save**.

Changing a vehicle never changes the price of a job already booked; booked jobs keep the prices they were quoted.
