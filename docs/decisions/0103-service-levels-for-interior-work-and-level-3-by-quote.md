---
id: 103
title: "Condition levels apply only to interior work, and Level 3 is booked by quote"
summary: "Only Full Detail and Interior Only take a condition level. Level 1 adds nothing, Level 2 adds 10% to price and time, and Level 3 is quoted by hand. Both rules are stored with each pricebook version."
date: 2026-11-14
area: pricing
status: accepted
audience: [owner, staff, developer]
visibility: internal
updated: 2026-11-14
supersedes: [docs/decisions/0013-condition-levels.md, docs/decisions/0065-condition-lengthens-service-time.md]
superseded_by: []
related: [docs/reference/pricing.md, docs/reference/booking-flow.md, docs/reference/public-api.md, docs/reference/pricebook-changes.md, docs/reference/control-app.md, data/pricing-rules.yaml, data/services.yaml, docs/decisions/0013-condition-levels.md, docs/decisions/0033-pricebook-versions-and-line-snapshots.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0065-condition-lengthens-service-time.md, docs/decisions/0099-quote-requests-with-photos.md]
---

# 0103: Condition levels apply only to interior work, and Level 3 is booked by quote

**Status:** accepted · **Date:** 2026-11-14 · **Area:** pricing

## Context

Condition levels (decision 0013) added 0%, 10% or 20% to the price of Full Detail, Interior Only and Exterior Only, and from decision 0065 to their service time too. On the new website the levels are called service levels, and what they describe (pet hair, spills, stains, mold) is interior work. An exterior-only job does not get harder in the same way. The worst interiors also vary too much for one percentage: some take an hour more, some a day more. The owner set the new rules on 2026-11-14.

## Decision

- **Only the services that cover the interior take a condition level:** Full Detail and Interior Only. Exterior Only, both paint corrections, Headlight Restoration and Motorcycle Detail have no condition level at all. Exterior Only loses the 10% and 20% it had.
- **Level 1 is preselected and adds nothing. Level 2 adds 10% to the price and to the main service's service time,** as decision 0065 set, for Full Detail and Interior Only only.
- **Level 3 has no price and no time.** It is booked by quote, the same way as a vehicle in a class booked by quote (decision 0099). The website sends a quote request carrying the service, the level and any add-ons; the control app takes the price and the time on site by hand, as a quote record (decision 0059), with the Level 2 price shown beside it for reference.
- **Both rules are pricebook data, stored with each version** (decision 0033): which services take a level (`condition_applies` in data/services.yaml), and which levels are booked by quote (`booked_by_quote` in data/pricing-rules.yaml). The change takes effect when the owner publishes the new version, with the usual review of booked jobs.
- **Jobs already booked keep their quoted prices,** and past jobs keep their condition lines. The review lists a booked Exterior Only job with a condition line, which would lose it, and a booked Level 3 job, which the new version can't price; keeping the booked price is the default for both.
- **A job priced by hand is never re-priced by a pricebook change,** whether it came from a quote request or a Level 3 booking: its quote is marked priced by hand, and the review leaves it out.

## Alternatives considered

- **Keep a percentage for Level 3.** Simpler, but the owner would under-price the worst interiors or over-price the rest; a hand quote fits them.
- **Keep the rule in code, or on the service record.** A change would then reach booked jobs and old versions at once. Stored with each version, it changes only when a version is published, and older versions still say what they priced.
- **A separate "Exterior condition" level.** Nothing the owner sees on the outside varies enough to need it.

## Consequences

- The booking flow puts the service step before the condition step, which appears only for Full Detail and Interior Only, so the service cards show prices before any condition adjustment.
- The public API refuses a condition with any other service, and answers `ask_for_quote` for Level 3, with no price or time; the booking endpoint can never book one.
- A Level 3 job's time on site is set by hand, so the full-day flag follows the owner's time, not a percentage.
- This changes decision 0013 (which services and the 20%) and decision 0065 (which services the condition lengthens, and Level 3's time).
