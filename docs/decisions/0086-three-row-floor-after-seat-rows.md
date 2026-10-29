---
id: 86
title: "The three-row floor runs after seat rows are final, so every three-row vehicle under the Medium line is Medium"
summary: "The three-row floor moves from a rule to the last step after the rules, so a Small model year with three seat rows from any source, minivans included, is Medium."
date: 2026-10-28
area: vehicles
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: []
related: [docs/decisions/0082-size-based-vehicle-classes.md, docs/decisions/0085-size-class-fixes-after-the-first-dry-run.md, data/size-classes.yaml, docs/reference/vehicle-classification.md]
---

# 0086: The three-row floor runs after seat rows are final, so every three-row vehicle under the Medium line is Medium

**Status:** accepted · **Date:** 2026-10-28 · **Area:** vehicles

## Context

Decision 0082 made every vehicle the third-row data marks "always" three rows at least Medium, with a rule tried before the Small rule. Decision 0085 then made EPA minivans and listed minivans always three rows when their seat rows are worked out, which happens after the rules. A minivan under 490 cubic feet therefore matched the Small rule and got three rows. The owner's second `apply_size_classes` dry run refused the switch: Small has no three-row price, for 14 model years such as the 2008 to 2009 Mazda5 and the 1984 to 1991 Dodge Caravan.

## Decision

1. **The three-row floor is a step, not a rule.** It runs last, after the pickup steps, the EPA size class fallback and smoothing. Once seat rows are final, a Small model year with three seat rows takes Medium, with three rows. The cause of the three rows does not matter: the third-row data's "always", an EPA minivan class, or the minivan list. The rule "Three-row vehicles under the Medium line" is removed, so Small is now rule 120.
2. **An optional third row still does not count:** the year stays Small and the size is asked.
3. **Model overrides and review queue decisions are left alone.**
4. The classes are a setting, `three_row_floor` in `data/size-classes.yaml`. The "how" line says the floor lifted the year and names the rule that gave Small.

## Alternatives considered

- **Add minivan conditions to the floor rule.** Seat rows would then be decided in two places, the rule and the size step, and could disagree again.
- **Price Small with three rows.** The owner kept the price book.

## Consequences

The price book check no longer finds Small with three rows from always-three-row vehicles and minivans. A Small model year with an optional third row would still be counted for both two and three rows; the dry run names any such year.
