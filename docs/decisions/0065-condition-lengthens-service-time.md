---
id: 65
title: "The condition level lengthens the main service's service time"
summary: "The condition percentage (0%, 10% or 20%) is added to the main service's one-person service time as well as its price, for Full Detail, Interior Only and Exterior Only only."
date: 2026-10-17
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, data/pricing-rules.yaml, docs/reference/booking-flow.md, docs/decisions/0013-condition-levels.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0058-service-times-exclude-setup-and-breakdown.md, docs/decisions/0059-quoted-price-is-price-of-record.md]
---

# 0065: The condition level lengthens the main service's service time

**Status:** accepted · **Date:** 2026-10-17 · **Area:** pricing

## Context

The condition level (decision 0013) added 0%, 10% or 20% to the price of Full Detail, Interior Only and Exterior Only, but not to their time. A dirtier vehicle takes longer as well as costing more, so the service time, the time on site and the full-day flag understated those jobs. The owner set the rule on 2026-10-17.

## Decision

- The condition level's percentage is added to the main service's one-person service time as well as its price, for Full Detail, Interior Only and Exterior Only only.
- The condition line carries its extra time in its line snapshot: the base service hours times the percentage, unrounded.
- Add-ons, maintenance plans, and setup and breakdown are never adjusted.
- The add-on hours are then added, the two-person factor applied, and the service time rounded to the nearest 15 minutes once, as before. Time on site follows from that.
- The rule uses each version's stored condition percentages; nothing else is stored, so it applies without reloading the pricebook.
- Quotes already issued and appointments already booked keep the times they were given.

Examples: the RAV4 worked example stays $355 and becomes 7 hours of service and 8 hours on site, a full day. A two-door Coupes & Sedans Full Detail at level 3 is 3.5 hours of service and 4.5 on site; a two-person 2-row Midsize SUV Full Detail at level 3 is 4 hours of service and 4.5 on site.

## Alternatives considered

- **A separate time percentage per condition level.** More settings to keep in step, with no difference today; the owner set the same percentage for both.
- **Round the condition time on its own line.** Would round twice; rounding once at the end keeps the total closest to the real time.

## Consequences

Higher condition levels can push a job into a full day. Line hours are now stored exactly, to seven decimal places, so the snapshot holds the unrounded extra time. A pricebook draft published later lists booked jobs at levels 2 and 3 as changing service hours, because they were booked before condition time counted; the owner decides each one as usual.
