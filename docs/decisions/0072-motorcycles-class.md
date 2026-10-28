---
id: 72
title: "Motorcycles become a vehicle class with one service, Motorcycle Detail at $100"
summary: "Every motorcycle model goes to a new Motorcycles class with one price, booked online; its only service, Motorcycle Detail, is a flat $100 with no condition level or add-ons, 1 hour of service, up to two a day."
date: 2026-10-22
area: pricing
status: superseded
audience: [owner, developer]
visibility: internal
updated: 2026-10-28
supersedes: []
superseded_by: [docs/decisions/0083-applying-the-size-based-classes.md]
related: [data/vehicle-classes.yaml, data/services.yaml, data/price-matrix.csv, data/booking-rules.yaml, docs/reference/pricing.md, docs/reference/vehicle-classification.md, docs/decisions/0058-service-times-exclude-setup-and-breakdown.md, docs/decisions/0060-vehicle-classification-rules-are-data.md, docs/decisions/0061-staff-authorized-per-service.md, docs/decisions/0071-vehicle-facts-per-model-year-and-source.md]
---

# 0072: Motorcycles become a vehicle class with one service, Motorcycle Detail at $100

**Status:** superseded by [0083](0083-applying-the-size-based-classes.md) for the Motorcycle Detail's time, now 2 hours of service; the rest stands · **Date:** 2026-10-22 · **Area:** pricing

## Context

Motorcycles joined the vehicle catalog in Phase 2 Step 1 (decision 0071), shown in the same year, make and model lists as cars, but had no vehicle class and no price, so a customer could pick a motorcycle and not book it. The job history has two motorcycles, imported as custom lines at the price charged. Phase 1 already allows a vehicle class with a single price and no size variant. The owner set the class and its price for Phase 2 Step 2 on 2026-10-22.

## Decision

1. **A seventh vehicle class, Motorcycles,** with one price and no size variant (its size variant measures "none"), booked online, with its own photo card.
2. **A classification rule sends every catalog model with vehicle type motorcycle to it.** It is the first launch rule, so no EPA or weight rule can catch a motorcycle.
3. **One service, Motorcycle Detail,** offered only for Motorcycles and the only service priced for Motorcycles: a flat $100 in the price matrix, with no condition level and no add-ons.
4. **Its time:** one person, 1 hour of service time, which is 2 hours on site with the 30-minute setup and breakdown (decision 0058).
5. **Up to two a day,** the same jobs-per-day setting as Monthly Maintenance, in `services_sharing_a_day` in `data/booking-rules.yaml`. A Motorcycle Detail and a Monthly Maintenance can share a day (confirmed by the owner on 2026-10-22).
6. **Sales tax applies as usual,** and the owner, as a manager, is authorized for it like every service (decision 0061).

## Alternatives considered

- **Leave motorcycles off the price list,** quoted by hand as custom lines. Customers who pick a motorcycle in the booking form could not book.
- **Price motorcycles by size,** such as touring and sport. The owner set one price; a size variant can be added to the class later as a record, with no code change.

## Consequences

The booking form's photo-card fallback has seven cards. On the server, where pricebook version 1 is already published, `load_pricebook` adds the class and the service and puts the $100 price in a new draft for the owner to publish from the control app. The two imported motorcycle jobs keep their custom lines and no vehicle class; booked jobs never change. Motorcycle models are labeled in the booking form so a Honda Gold Wing and a Honda Accord are easy to tell apart.
