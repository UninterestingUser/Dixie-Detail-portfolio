---
title: Using the catalog screens
summary: A short guide to the control app's Catalog tab - lookup and test prices, overrides, rules and their preview, class settings, the review queue, differences, approvals and each model's history.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-24
tags: [operations, vehicles, classification, control-app, phase-2]
related: [docs/decisions/0079-approval-list.md, docs/decisions/0077-linking-vehicles-to-the-catalog.md, docs/operations/linking-vehicles.md, data/approval-spot-checks.yaml, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/decisions/0075-unpublished-years-and-canadian-nameplates.md, docs/reference/vehicle-classification.md, docs/operations/classifying-vehicles.md, docs/reference/control-app.md]
---

# Using the catalog screens

The **Catalog** tab in the control app is where the owner sees and settles how vehicles are classified ([decision 0076](../decisions/0076-catalog-screens-in-the-control-app.md)). It has six screens, linked along its top: **Look up**, **Review queue**, **Rules**, **Differences**, **Approvals** and **Classes**. Everyone signed in can look; only a manager (the owner) can change anything, and the screens hide the controls from anyone else. How classification works is in [../reference/vehicle-classification.md](../reference/vehicle-classification.md).

## Look up a vehicle

1. Type the year, then the make, then the model. Each box's list narrows as you type and to what the year and make allow. Other spellings work, such as "GLE-Class" for the GLE.
2. Tap **Look up**. The screen shows the vehicle class, the size (or the question the customer will be asked), the price basis, how customers book it, and **How** the class was reached: a rule, a model override, a review queue decision, the nearest classified year (for a year the EPA has not published), or that it waits in the review queue.
3. **Facts for the year, by source** shows what each source says: EPA size class, body style, curb weight, length, seat rows, cab style, and so on. Your own figures are marked **Yours**.
4. **Test price** prices any service for the class and size shown, or any other, from the pricebook in effect today. Nothing is saved.
5. **Every year of this model** lists each year's class and how it was reached; tap a year to see it.

A vehicle not in the catalog, or before 1984, shows that the customer chooses from the photo cards.

## Overrides

On a model's screen, under **Overrides**:

- **Set an override for the class or size.** Pick the years (leave both empty for every year), the vehicle class, and the size: worked out from the facts, always asked, or one size. Add a note saying why. It applies at once to that model and beats every rule. An override for the same years replaces the one there.
- **Set the third-row flag.** Always, never or optional (asked) for the years chosen, or **Clear** to go back to the third-row list and NHTSA. It is recorded as your own seat rows.
- **Clear** removes an override or a review queue decision; the rules decide those years again.

A **customer's vehicle** that is lifted or modified gets its own class on its edit screen (Customers, the customer, **Edit** on the vehicle), under **Class override**. It beats the catalog and the model's overrides. **Go back to the catalog's class** clears it. The model's screen lists customers' vehicles with their own class.

## Rules

**Rules** lists the rules in the order they are tried, each written out in plain words, such as "EPA size class Small Sport Utility Vehicle 2WD or Small Sport Utility Vehicle 4WD and curb weight over 4,500 lb → Midsize SUVs". Launch rules from the data file are marked, and so is one you have edited, which the data file then leaves alone.

- **Add a rule** or **Edit**: give a name, a position (rules are tried from the lowest up; 75 goes between 70 and 80), the vehicle class, and the conditions, one fact per row. A list fact takes values one per line; a weight, size or year takes one or both ends of a range. Leave a row's fact empty to drop it.
- **↑ and ↓** move a rule one place; **Disable** and **Enable** switch it off and on.

Every one of these shows the **preview** first: how many model years of how many models would change, grouped by old and new class, with each group's model years behind **The model years**. Nothing changes until you tap **Confirm and apply**, which saves the rule and applies it to the whole catalog (a few seconds). **Back to editing** returns to the form. If the catalog changed since the preview, it is shown again to check.

## Class settings

**Classes** lists each vehicle class with what its size variant measures, how it is booked, its photo card caption and how many model years it has. **Edit** changes them. A change to what the size measures shows the preview of every model year whose size would change; a change between booking online and asking for a quote shows the model years it reaches; both apply only when confirmed. A new caption saves at once. Size variants and retiring a class stay in the Django admin.

## The review queue

**Review queue** lists the model years no rule settles, newest model years first, 50 to a page, with a count beside the tab. The schedule (the home screen) says how many wait while the queue is not empty. Filter by **Year** and by **Reason**: no rule matches, the trims split on a condition, or the sources disagree.

Each model year shows why it is there, the facts that matter, the class it keeps meanwhile if it was live, and a **suggestion**: the class of the rule its trims straddle, or of the model's nearest classified year.

- **Accept** takes the suggestion in one tap.
- **Photo cards** takes it out of the queue with no class; the customer picks a photo card.
- **Pick another class or set the size** chooses any class, with the size from the facts, always asked, or fixed.
- To settle many at once, tick them (or **Pick every model year on this page**), then **Accept suggestions** or **Photo cards** at the bottom. A model year with no suggestion is skipped and stays in the queue. The note box is saved with the decision.

A decision applies at once and stays until you clear it on the model's screen. A model override for the year beats it.

## Differences

**Differences** lists each customer's vehicle, linked to the catalog by `link_vehicles` ([linking-vehicles.md](linking-vehicles.md)), whose own class or size, as imported or entered, differs from the catalog's. Each shows both, the customer, and a link to the model's screen ([decision 0077](../decisions/0077-linking-vehicles-to-the-catalog.md)). Pick one of three, with an optional note:

- **Keep imported: this vehicle only** makes the vehicle's class its own override, for a lifted or modified vehicle. It beats the catalog from then on.
- **Accept the catalog's** gives the vehicle the catalog's class, and the catalog's size when it fixes one.
- **Every 2014 to 2019 RAV4: Midsize SUVs** (the years and class shown are the vehicle's) sets a model override for the years the catalog classes alike around this vehicle's year. A class that differed takes its size from the facts; a size that differed is fixed for those years. Other vehicles of the model in those years may then differ, and show here.

Past jobs keep their prices whichever you pick. A vehicle that no longer differs leaves the list. A vehicle with no year is not listed: its class depends on the year, so it is compared once the year is filled in.

## Approvals

**Approvals** is where Phase 2 is signed off ([decision 0079](../decisions/0079-approval-list.md)). It lists every model with the make and name of a vehicle in the job history, whether or not the vehicles have a year, every model on the spot-check list in [data/approval-spot-checks.yaml](../../data/approval-spot-checks.yaml), every model whose years are in different classes, and every model approved before, with how many are approved. It shows the models still waiting; **Show** picks approved ones or all, and **Listed for** filters by why a model is there.

Each model shows once, as its year ranges: the years in a row with the same class, size and **How**. For each range:

- **Approve** records it as it stands, with your name, the time and an optional note.
- **Change** picks another class and size, sets a model override for exactly those years, and approves the result.

A range waiting in the review queue can only be changed. When a later change to a rule, an override, the third-row flag, a queue decision or a class setting alters an approved range, by its years, class, size or how, the approval is cleared and the model shows again, saying which change cleared it. Spot-check entries the catalog does not have are listed at the bottom.

## History

Every change to a rule, an override, the third-row flag, a class setting, a queue decision, a vehicle's class or an approval is logged with who made it and when, and so is each `classify_vehicles` and `link_vehicles` run. A model's screen lists, under **History**, every change that reached it, with the years it changed from one class or size to another. **Rules** shows the latest rule, class and run changes.

## When something looks wrong

- **A model year shows the old class after a rule change.** The change was not confirmed: the preview changes nothing. Make the change again and tap **Confirm and apply**.
- **The EQE or EQS SUV has the sedan's weight.** Reload the Canadian specifications from the cache once, then apply the rules, as in [classifying-vehicles.md](classifying-vehicles.md#before-the-first-run).
