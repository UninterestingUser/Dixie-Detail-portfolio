---
id: 69
title: "How the control app books, re-prices, staffs and publishes"
summary: "Rules for the job, staff and pricebook screens: every price from a quote, re-pricing only with a reason, one on-site adjustment line, managers by role, automatic assignment for one-person jobs."
date: 2026-10-18
area: control-app
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-18
supersedes: []
superseded_by: []
related: [docs/guides/booking-a-job.md, docs/guides/assigning-staff.md, docs/guides/editing-the-pricebook.md, docs/reference/control-app.md, docs/reference/pricebook-changes.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0061-staff-authorized-per-service.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md]
---

# 0069: How the control app books, re-prices, staffs and publishes

**Status:** accepted · **Date:** 2026-10-18 · **Area:** control-app

## Context

Decisions 0033, 0059 and 0061 set the rules for prices, quotes and staff, and pricebook-changes.md the steps for publishing. Building the appointment, staff and pricebook screens in Phase 1 needed a few smaller choices those records leave open: how an owner's edit re-prices a job, how a final price is recorded, who counts as a manager, and when automatic assignment applies.

## Decision

- **Every price comes from a quote.** Booking a job, each visit of a series, a changed job and a job given the new price at a publish all issue a quote from the pricing engine and copy its lines (decision 0059). The booking form's live price calls the same engine and stores nothing.
- **Pricebook by date.** A job is priced from the version in effect on its own date, so the visits of a series can span a price change. A date before the first version took effect, such as a past job entered late, uses the version in effect today.
- **Changing a job.** Changing its date, time, vehicle, address or notes never re-prices it. Changing what it is priced from (service, vehicle class, size, condition, add-ons or crew) issues a new quote and needs a reason, which is kept in the job's change history. Only booked jobs are re-priced; completed and canceled jobs keep their prices.
- **Final price.** The owner types the final price; the difference from the lines becomes one on-site adjustment line with its reason. Typing a new final price replaces that line, and typing the lines' own total removes it.
- **Series.** A Monthly series repeats on the same day of the month and a Quarterly series every three months, at the same time of day, falling back to the month's last day when a month is shorter. A series has 2 to 24 visits.
- **Managers.** A staff member with the owner role is a manager; a signed-in superuser acts as one. Only a manager changes authorizations or the pricebook, or assigns someone not yet authorized.
- **Automatic assignment** applies to one-person jobs only. A two-person job, such as Monthly Maintenance, always shows the prompt, because one qualified person cannot fill it.
- **A crew of a different size** recalculates the service time and time on site from the job's own lines and the crew rules of the version it was priced from. The price does not change.
- **Publishing.** A custom amount at a publish becomes the job's total before tax, through the on-site adjustment line. A job the new version can no longer price, such as one whose service was removed, can be kept or given a custom amount; its service is then changed from the job page if needed.
- **The price matrix on screen** lists the maintenance plans as the file does, worked out from their rule and marked as set by it, so they are changed through Full Detail or the percentage.

## Alternatives considered

- **Re-price a job whenever it is saved.** Would change booked prices without the owner meaning to, against decision 0059.
- **A free-form final price with no line.** The lines would no longer add up to the total, and the reason would have nowhere to live.
- **A separate manager flag on staff records.** Not needed while the owner is the only manager; a later decision can add one when a helper becomes a manager.
- **Automatic assignment on two-person jobs.** Would leave a two-person job with one person and no prompt.

## Consequences

The owner can book, change and complete every job from the phone, and every price on a job can be traced to a quote, a logged publish choice or an adjustment with a reason. Texting customers about a changed price waits for Phase 4, and checking a changed job against the availability rules for Phase 3.
