---
id: 79
title: "The approval list: models in the job history, a spot-check list and mixed-class models, approved by year range and cleared by any change"
summary: "The owner approves each year range of each listed model as it stands, with who and when recorded; a later change that alters an approved range clears its approval so the model shows again."
date: 2026-10-24
area: vehicles
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: [docs/decisions/0083-applying-the-size-based-classes.md]
related: [data/approval-spot-checks.yaml, docs/operations/using-the-catalog-screens.md, docs/reference/vehicle-classification.md, docs/overview/roadmap.md, docs/decisions/0076-catalog-screens-in-the-control-app.md, docs/decisions/0077-linking-vehicles-to-the-catalog.md]
---

# 0079: The approval list: models in the job history, a spot-check list and mixed-class models, approved by year range and cleared by any change

**Status:** superseded by [0083](0083-applying-the-size-based-classes.md) for the mixed-class models, which the list no longer holds, and the spot-check list, replaced when the list started over; approving by year range and clearing on any change stand · **Date:** 2026-10-24 · **Area:** vehicles

## Context

Phase 2 is done when the owner approves the class for every model in the job history and a spot-check list (the roadmap). A model is classified per model year (decision 0073), so one model can be in several classes over its years, and one approval for the whole model would hide that. Rules and overrides keep changing in the control app (decision 0076), so an approval given before a change may no longer describe what customers see.

## Decision

1. **What is listed:** every catalog model of a vehicle in the job history (linked by decision 0077), every model on the spot-check list in `data/approval-spot-checks.yaml`, every model whose years are in different classes (the `classify_vehicles` report's list, worked out live), and every model approved before.
2. **The spot-check list** holds about 40 models that sit near a class boundary, such as the Wrangler, Bronco, 4Runner, Tahoe, Suburban, RAV4, CR-V, Outback, Model Y, Highlander, Telluride, Tacoma, F-150, F-250, Ram 1500 and 2500, Sienna, Transit and Sprinter, each with why it is there. The owner edits the file to add or remove one.
3. **Each model shows once, as its year ranges:** each run of consecutive model years with the same class, size and "how" line, with Approve and Change per range. Change sets a model override for exactly that range and approves the result, since the owner chose it. A range waiting in the review queue can only be changed.
4. **An approval keeps the range as approved,** with who approved it and when, and an optional note.
5. **Any change clears what it alters.** After every logged change (a rule, override, third-row flag, queue decision, class setting or `classify_vehicles` run), an approval whose range no longer exists exactly as approved, by years, class, size or how, is cleared, naming the change. The model shows on the list again with that change.

## Alternatives considered

- **Approve a model as a whole.** A model whose years differ would be approved without each range being seen.
- **Clear only on a change that alters the class.** A range now reached by another rule, or with its size now asked, is not what was approved, and the owner should see it.
- **Keep the mixed-class models in the data file.** They change whenever the data or rules change, so they are worked out live instead.

## Consequences

The list can be long while many models have years in different classes; it filters by what is waiting and why a model is listed. Approvals are records the owner can trace, and the model's history shows each one. A rule edit that changes only a rule's name changes the "how" line, so it clears the approvals that rule reached.
