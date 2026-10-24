---
id: 76
title: "The control app's catalog screens: managers change, a rule or class setting is previewed, every change is logged"
summary: "The catalog screens move classification out of the Django admin: rule and class changes apply on confirming a preview, the rest at once, each logged with its effect."
date: 2026-10-23
area: control-app
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-23
supersedes: []
superseded_by: []
related: [docs/operations/using-the-catalog-screens.md, docs/reference/vehicle-classification.md, docs/reference/control-app.md, docs/decisions/0060-vehicle-classification-rules-are-data.md, docs/decisions/0068-control-app-https-static-and-sign-in.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/decisions/0073-classification-per-model-year.md]
---

# 0076: The control app's catalog screens: managers change, a rule or class setting is previewed, every change is logged

**Status:** accepted · **Date:** 2026-10-23 · **Area:** control-app

## Context

Decision 0060 asked for owner-editable rules with a preview, overrides, class settings and a review queue; decision 0073 left them in the Django admin and the `classify_vehicles` command until the control app had screens. Building those screens (Phase 2 Step 3) needed a few choices those records leave open: who may change what, when a change reaches the catalog, how the owner settles a model year in the review queue, and how a change is traced.

## Decision

- **Everyone signed in can look; only a manager changes.** Managers are as in decision 0069. Looking a vehicle up, the rules, the class settings and the review queue are open to every signed-in user, and every change is refused for anyone else.
- **A rule or class setting is applied when the manager confirms its preview.** Adding, editing, moving, disabling or enabling a rule, and changing what a class's size variant measures, first shows every model year that would change, grouped by old and new class. Confirming saves it and applies it to the whole catalog at once, so the booking lookup has it without waiting for `classify_vehicles`. If the catalog changed between the preview and the confirmation, the preview is shown again. A change to how a class is booked shows which model years it reaches; a photo card caption saves at once.
- **A model override, the third-row flag and a queue decision apply at once,** to that model only. The third-row flag is recorded as the owner's own seat rows for the years chosen, which beat the third-row list and NHTSA.
- **A review queue decision is its own record,** one per model year: a class, with its size fixed, always asked or from the facts, or the photo cards. A model override covering the year beats it; it beats the rules and the nearest-year class (decision 0075). The queue offers a suggestion for each model year: the class of the rule its trims straddle, or of the model's nearest classified year.
- **Moving a rule changes only that rule's position** when there is room between its new neighbors, so the other launch rules still follow the data file (decision 0074); otherwise every rule is numbered again in steps of 10.
- **Every change is logged** with who made it, when, a sentence saying what it was, and each model year whose class, size or review status it changed, before and after. A model's screen shows every change that reached it, and the changes made by `classify_vehicles` runs too.

## Alternatives considered

- **Save a rule and leave applying it to `classify_vehicles`.** The owner would need a server shell to see a change take effect, and the screen's preview could drift from what the command later does.
- **Settle queue items with one-year model overrides.** A model override could not send a model year to the photo cards, and the model's override list would fill with hundreds of one-year entries from the queue.
- **Show the history from each record's own change history only.** It would say a rule changed, but not which models it moved, so the model's screen could not show it.

## Consequences

The owner settles the review queue and changes the rules from the phone. The Django admin stays for size variants and retiring a class. A full-catalog apply takes a few seconds on the server, so a rule or class change waits that long after confirming. The log grows with every applied run; it is small rows, and can be trimmed later if needed.
