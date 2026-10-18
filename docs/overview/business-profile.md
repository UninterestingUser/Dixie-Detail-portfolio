---
title: Business profile
summary: Who Dixie Detail is, what it sells, where it works, how it is staffed and paid, and which tools it uses today.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [business, overview]
related: [data/business.yaml, data/service-area.yaml, data/services.yaml, docs/overview/project-goals.md]
---

# Business profile

Exact contact details, brand colors and profile links are in [data/business.yaml](../../data/business.yaml). This page explains them.

## What Dixie Detail does

Dixie Detail LLC is a mobile vehicle detailing business based in Calhoun, Tennessee, in McMinn County. The crew drives to the customer's home or workplace and details the vehicle there, using water and power at the address. The business is registered as an LLC with an EIN.

## Services sold

Ten services are on the price list: Full Detail, Interior Only, Exterior Only, 1-Step and 2-Step Paint Correction, Headlight Restoration, two add-ons (Carpet Extraction and Seat Extraction), and two maintenance plans (Monthly and Quarterly Maintenance). Ceramic wax is included in every detail, so there is no wax upgrade. A "Misc Services" line lets the owner add a one-off job at a custom price.

PPF Removal and Trim Restoration were sold in the past and will return once priced; for now they exist only in job history.

The full list, what each price depends on and who can book each service are in [data/services.yaml](../../data/services.yaml). How prices are built is in [../reference/pricing.md](../reference/pricing.md).

## Where Dixie Detail works

The service area is five Tennessee counties: Bradley, McMinn, Polk, Meigs and Hamilton. The owner can approve individual addresses outside that area; today one customer just over the state line in Cohutta, Georgia, is approved. Details are in [data/service-area.yaml](../../data/service-area.yaml) and [../reference/sales-tax.md](../reference/sales-tax.md).

All times are Eastern.

## How the business is staffed

The owner works alone today. Family members have helped as a second person on some jobs, and the plan is a two-person crew as the default later. Crews are one or two people; three-person crews are not planned.

## How customers pay

Customers pay at the time of service, with no deposit. Accepted methods are cash, card, Venmo, PayPal, Cash App and Bitcoin. Gift cards and prepayments happen occasionally. See [../reference/payments.md](../reference/payments.md).

## Brand

Red (#CC0000) is the main business color, with navy blue (#002D65) as the accent and white. The logo is a script wordmark. The website direction is in [../reference/website-and-seo.md](../reference/website-and-seo.md).

## Tools in use before the new system

| Tool | Used for | Fate |
| --- | --- | --- |
| WordPress with Yoast SEO | Public website | Replaced by the new Astro site at launch (Phase 5) |
| Setmore | Online booking and reminders; contacts only, it cannot export appointments | Retired at launch |
| Baserow | The owner's full record of customers, vehicles and appointments | Imported once, then retired. See [../reference/data-migration.md](../reference/data-migration.md) |
| Trustindex | Review widget on the website | Replaced by reviews on the new site |
| GnuCash | Double-entry books | Kept, fed by an export |
| VoIP phone line | The business number | Ported to Quo after carrier registration |

The domain's DNS already runs on the owner's free Cloudflare account.
