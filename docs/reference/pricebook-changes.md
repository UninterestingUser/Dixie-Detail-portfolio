---
title: When prices or services change
summary: How pricebook edits are published as versions with an effective date, why completed jobs never change, and how the owner decides case by case for booked jobs.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-18
tags: [pricing, pricebook, versioning]
related: [docs/guides/editing-the-pricebook.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/reference/pricing.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md, docs/architecture/data-model.md]
---

# When prices or services change

Completed jobs never change, and booked jobs change only when the owner says so. This is settled policy, built in Phase 1.

## What is built and what comes later

The pricebook screens in the control app do steps 1 to 5 and 7 below: the prices laid out like the price matrix, a draft copied from the latest published version, publishing with an effective date today or later, and the list of booked jobs the draft would change, each with its booked and new totals, a note when the new hours make it a full day, and a note when the job can no longer be priced, with a choice for each and every choice logged. The availability check in step 5 comes with Phase 3, and the text in step 6 with Phase 4. How to use the screens is in [../guides/editing-the-pricebook.md](../guides/editing-the-pricebook.md).

## Every appointment keeps its own copy of its prices

When a job is booked, each line is copied onto the appointment: the service, price, hours, condition level and any promotion. This line snapshot means a later pricebook edit cannot reach back into a booked or completed job. The lines come from the server's quote, so the price the customer saw is the price booked, and the control app never re-prices a booked job on its own ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)). The choices below are the owner's, so they raise no price-change alert; they are logged instead.

## Publishing a pricebook change

1. The owner edits the pricebook as a draft and publishes it with an effective date, today or later. Each publish is kept as a numbered pricebook version.
2. Completed and paid jobs are left alone; they show what was done and charged.
3. On publish, the control app lists every booked, not-yet-completed job on or after the effective date whose price, hours or service the change touches, and asks how to handle each one.
4. For each job the owner picks **Keep booked price** (the default), **Use new price**, which re-prices the job from the new version through a new quote, or a custom amount, which becomes the job's total before tax through an on-site adjustment line. "Keep all" and "Use new for all" handle a long list in one tap. A recurring Monthly or Quarterly series can be decided once for every visit left in it.
5. A removed service needs an explicit keep-as-is or a custom amount; its replacement service is then set from the job page. A service-hours change that would push a job into a full day, or make its day fail the availability check (such as overlapping a second Monthly Maintenance visit), is flagged before the owner confirms.
6. Where a price changes, a checkbox texts that customer the updated estimate, but only if they agreed to appointment texts.
7. Every choice is logged with the old and new amounts and who made it, and listed on the version's page. The website shows the new prices, and online bookings and jobs booked in the control app use them, from the effective date.

## Sales tax is not part of a pricebook change

Each job is taxed at the rate in effect for its address on the day of service, so a quarterly rate update flows into booked jobs without a repricing prompt. Because the change is not the owner's choice, the owner gets a push alert for each booked job it touches. See [sales-tax.md](sales-tax.md).
