---
title: When prices or services change
summary: How pricebook edits are published as versions with an effective date, why completed jobs never change, and how the owner decides case by case for booked jobs.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-17
tags: [pricing, pricebook, versioning]
related: [docs/decisions/0059-quoted-price-is-price-of-record.md, docs/reference/pricing.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md, docs/architecture/data-model.md]
---

# When prices or services change

Completed jobs never change, and booked jobs change only when the owner says so. This is settled policy, built in Phase 1.

## What is built and what comes later

Since Phase 1 Step 3 the system has pricebook versions, drafts copied from the latest published version, publishing with an effective date today or later, and the list of booked jobs a draft would change, each with its booked and new totals and service hours, a note when the new hours make it a full day, and a note when the job can no longer be priced. The control app screens that let the owner edit a draft, publish it and choose for each listed job (steps 3 to 7 below) come with the pricebook screens later in Phase 1, and the availability check in step 5 with Phase 3.

## Every appointment keeps its own copy of its prices

When a job is booked, each line is copied onto the appointment: the service, price, hours, condition level and any promotion. This line snapshot means a later pricebook edit cannot reach back into a booked or completed job. The lines come from the server's quote, so the price the customer saw is the price booked, and the control app never re-prices a booked job on its own ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)). The choices below are the owner's, so they raise no price-change alert; they are logged instead.

## Publishing a pricebook change

1. The owner edits the pricebook as a draft and publishes it with an effective date, today or later. Each publish is kept as a numbered pricebook version.
2. Completed and paid jobs are left alone; they show what was done and charged.
3. On publish, the control app lists every booked, not-yet-completed job on or after the effective date whose price, hours or service the change touches, and asks how to handle each one.
4. For each job the owner picks **Keep booked price** (the default), **Use new price**, or a custom amount. "Keep all" and "Use new for all" handle a long list in one tap. A recurring Monthly or Quarterly series can be decided once for every visit left in it.
5. A removed service needs a replacement or an explicit keep-as-is. A service-hours change that would push a job into a full day, or make its day fail the availability check (such as overlapping a second Monthly Maintenance visit), is flagged before the owner confirms.
6. Where a price changes, a checkbox texts that customer the updated estimate, but only if they agreed to appointment texts.
7. Every choice is logged with the old and new amounts. The website shows the new prices, and online bookings use them, from the effective date.

## Sales tax is not part of a pricebook change

Each job is taxed at the rate in effect for its address on the day of service, so a quarterly rate update flows into booked jobs without a repricing prompt. Because the change is not the owner's choice, the owner gets a push alert for each booked job it touches. See [sales-tax.md](sales-tax.md).
