---
title: Running costs
summary: What the finished system costs to run each month, item by item, with the date each figure was checked.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [costs, budget]
related: [data/integrations.yaml, docs/architecture/integrations.md]
---

# Running costs

The fixed monthly cost of the finished system is the phone service plus Google Workspace. Everything else is free or charged per use. Prices change; each row says when it was checked.

## Monthly and per-use costs

| Item | Cost (USD) | Checked | Note |
| --- | --- | --- | --- |
| Quo Starter plan | 19 per month as subscribed | 2026-10-08 | Includes the API, webhooks and free number porting |
| Carrier registration for texts | 19.50 once, then 1.50 per month | 2026-10-08 | Business path with an EIN; 15 to resubmit after a rejection |
| Automated texts | 0.01 per segment | 2026-10-08 | About six one-segment texts per job |
| Google Workspace Business Starter | About 7 per user per month on annual billing | June 2026 summary | The business was adding Workspace anyway |
| Google Maps Platform | 0 expected | 2026-10-07 | Free up to 5,000 traffic-aware routes and 10,000 address requests a month; needs a billing account |
| Cloudflare (DNS, Tunnel, website hosting) | 0 | 2026-10-07 | Free plan |
| Bitwarden Secrets Manager | Existing | 2026-10-13 | Already used by the owner |
| Tailscale | Existing | 2026-10-07 | Already used by the owner |
| Healthchecks.io | 0 | 2026-10-12 | Free plan, 20 checks; two are used |
| Off-site backups in Google Drive | 0 | 2026-10-13 | Uses Workspace storage already paid for; dumps are a few megabytes |
| Stripe | Per transaction, no monthly fee | From memory | Roughly 2.9% plus 30 cents for an online card payment; confirm on Stripe's pricing page |
| Government data (EPA, NHTSA, Census, Tennessee Revenue), GnuCash | 0 | 2026-10-07 | Free sources and free software |
| BTCPay Server (Phase 7) | 0 | 2026-10-07 | Self-hosted |

## Contingency cost

If home-server outages recur, the same Docker stack can move to a cloud server for about $14 to $29 a month (server plus provider backups). The trigger is more than one outage a month during booking hours, or any outage over four hours.

## Costs that go away at launch

WordPress hosting, Setmore if on a paid plan, and the review widget if it is paid.
