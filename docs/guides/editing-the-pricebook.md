---
title: Editing and publishing the pricebook
summary: How to read the prices in the control app, change them in a draft, publish the draft with an effective date, and decide what happens to each booked job the change touches.
audience: [owner]
visibility: internal
status: current
updated: 2026-10-18
tags: [guides, pricebook, pricing, versioning, control-app]
related: [docs/reference/pricebook-changes.md, docs/reference/pricing.md, docs/reference/control-app.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, data/price-matrix.csv]
---

# Editing and publishing the pricebook

Prices live in numbered pricebook versions. A published version never changes; a change is made in a draft and published with an effective date. Completed jobs never change, and booked jobs change only as you choose. The rules are in [pricebook-changes.md](../reference/pricebook-changes.md). Only a manager edits or publishes.

## Read the prices

Tap **Pricebook**. It opens on the version in effect today, laid out like [data/price-matrix.csv](../../data/price-matrix.csv): one table per service, in the file's order, with each vehicle class and size, its one-person service hours and its price. Monthly and Quarterly Maintenance are worked out from Full Detail by their rule and marked "Rule". Below the tables are the rules: the maintenance percentages, the condition levels and the crew numbers. The buttons at the top open other versions.

## Change prices in a draft

1. Tap **Start a draft**. The draft is the next version number, a copy of the latest published prices. There is one draft at a time.
2. Change any price or hours. To stop offering a combination, tick its **✕** box. The maintenance percentages and condition percentages can be changed in the rules.
3. Add a note on what changed, and tap **Save draft**. A number that cannot be read stops the save and nothing is changed. Customers and booked jobs see nothing until you publish.

To throw a draft away, tap **Discard this draft**.

## Publish

1. In the draft, tap **Publish…**, pick the effective date (today or later) and tap **Show the booked jobs this changes**.
2. The list shows every booked job on or after that date whose price, hours or service the draft changes, with the reason, such as "Price changes from $250.00 to $300.00", and a warning when the new hours make it a full day.
3. For each job choose:
   - **Keep booked price**, the default;
   - **Use new price**, which re-prices the job from the new version;
   - **Custom amount**, typed in the box, which becomes the job's total before tax through an on-site adjustment line.
   A job the new version can no longer price, such as one whose service was removed, can only be kept or given a custom amount; change its service from the job page afterwards if needed.
4. For a long list, **Keep all and publish** and **Use new for all and publish** decide every job in one tap. A Monthly or Quarterly series with several visits in the list can be decided once for every visit left.
5. Tap **Publish version N**.

The version is published with that date. Jobs booked for that date or later, online or in the control app, use the new prices. Every choice is logged with the old and new amounts and who made it, and listed on that version's page under "Booked jobs decided when this version was published". Texting customers about a changed price comes in Phase 4, and checking a lengthened job against the availability rules in Phase 3.
