---
id: 106
title: "Headlight Restoration is an add-on, and which add-ons go with which service is pricebook data"
summary: "Each add-on goes only with the services its pricebook version lists; Headlight Restoration becomes one, for Full Detail, Exterior Only and paint correction; a manager can override with a reason."
date: 2026-11-18
area: pricing
status: accepted
audience: [owner, staff, developer]
visibility: internal
updated: 2026-11-18
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, docs/reference/pricebook-changes.md, docs/reference/booking-flow.md, docs/reference/public-api.md, docs/reference/control-app.md, docs/guides/booking-a-job.md, data/services.yaml, docs/decisions/0033-pricebook-versions-and-line-snapshots.md, docs/decisions/0058-service-times-exclude-setup-and-breakdown.md, docs/decisions/0094-how-the-availability-check-places-and-shares.md, docs/decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md]
---

# 0106: Headlight Restoration is an add-on, and which add-ons go with which service is pricebook data

**Status:** accepted · **Date:** 2026-11-18 · **Area:** pricing

## Context

Before this change, any add-on could go with any main service: Seat Extraction could be booked with Exterior Only, which never touches the seats. Headlight Restoration was a main service, so it could be booked on its own. The owner set the rules on 2026-11-18, during the Phase 3 acceptance changes.

## Decision

- **Headlight Restoration is an add-on.** It goes with Full Detail, Exterior Only, 1-Step Paint Correction or 2-Step Paint Correction. It can't be booked on its own or with Interior Only. Its price and time don't change. Like every add-on, it adds its service hours and no setup or breakdown of its own (decision 0058).
- **Carpet Extraction and Seat Extraction go only with Full Detail or Interior Only,** the services that cover the interior.
- **The rules are pricebook data, stored with each version.** `goes_with` in `data/services.yaml` lists the services each add-on goes with. `load_pricebook` stores the rules with the version (`AddOnFit`), and a draft copies them from the version it starts from, like the condition rules (decision 0103). An add-on goes only with the services listed for it.
- **The public API offers only the add-ons that fit.** Each service in the pricebook answer lists its add-ons. The price table holds only fitting sets. A quote, quote request or offline request with another add-on is refused, naming the add-on and the service.
- **The control app applies the same rules, with a manager's override,** as it does for the scheduling rules (decision 0094). A manager can add another add-on with a reason. The reason is logged with the job as a rule override, and the job page shows it. Anyone else picks another add-on. Changing a job booked that way keeps its add-ons without asking again, unless its service or add-ons change.
- **The change comes as a new pricebook version.** The migration gives every existing version the rule it was published with: any add-on with any main service or maintenance plan. After the deploy, `load_pricebook` makes Headlight Restoration an add-on and loads the new rules as a draft, which the owner publishes. Booked jobs keep their lines (decision 0033). The booked-job review lists each booked job that breaks the new rules. Such a job is re-priced with its add-ons as booked, so the owner can keep it, take the new price or give a custom amount. A job booked alone as Headlight Restoration can no longer be priced, so the owner keeps it or gives a custom amount. A job a manager booked with an add-on override is not listed for that reason.

## Alternatives considered

- **A fixed list in code.** The fit would change without a pricebook version, re-pricing nothing and leaving no record of which rules a job was priced under.
- **Keep Headlight Restoration bookable alone as well.** The owner wants it booked with a detail or paint correction only.
- **No override in the control app.** Some customers ask for an unusual combination on the phone. The scheduling rules already allow a manager's logged override, so the add-on rules work the same way.

## Consequences

- Between the deploy and publishing the draft, Headlight Restoration is an add-on under a version that has no rules for it, so it isn't offered. Publish the draft the same day: the steps are in [pricebook-changes.md](../reference/pricebook-changes.md).
- The website's add-on choices change with the service picked, and a picked add-on that doesn't fit the new service is dropped.
- The price table grows to every set of fitting add-ons, up to three with Full Detail.
