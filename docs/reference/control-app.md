---
title: Control app
summary: The private web app the owner and staff use to run the business, the areas it will contain, and the rules it follows.
audience: [owner, staff, developer]
visibility: internal
status: planned
updated: 2026-10-13
tags: [control-app, back-office]
related: [docs/architecture/network-and-access.md, docs/overview/roadmap.md]
---

# Control app

The control app will be a private web app on the home server, opened in a browser on the Fedora workstations and installed to the Pixel's home screen. It is reached only over the owner's Tailscale network, at `https://server.example-tailnet.ts.net`, and is never exposed to the public internet. Phase 1 builds its first screens; later phases add the rest. At the end of Phase 0 only the health page exists.

## Areas

| Area | What the owner will do there | Phase |
| --- | --- | --- |
| Today and calendar | See the day's job with address, vehicle, total and payment method; send "on my way"; mark the job complete and paid | 3 to 4 |
| Customers | Contact details, second contacts, vehicles, notes, and every past appointment, payment and text; resolve quiet-matching flags | 1, 3 |
| Pricebook | Services, vehicle classes, prices, add-ons, descriptions and photos; publish versions to the website | 1 |
| Promotions | Percent or dollar discounts, date windows, promo codes and a website banner | 6 |
| Billing | Invoices, payments by method, refunds and receipts | 4 |
| Bookkeeping | The sales journal, processor fees, sales tax owed by period and GnuCash exports | 6 |
| Staff | Helpers, their job assignments and what each is owed | 6 |
| Marketing | Where each customer came from, review-request results, and follow-up campaigns to chosen groups | 6 |
| Messages | Text templates and a log of everything sent and received | 4 |
| Vehicles | The class mapping, override rules and the review queue | 2 |
| Settings | Hours, service area, booking rules, buffers and user logins | 1 onward |

## Rules the control app follows

- **Linux-first by being a web app.** Nothing to install or update on any workstation. It can be wrapped in its own desktop window later without a rewrite.
- **Changes are traceable.** Every price or description change records who made it and when, and can be undone.
- **GnuCash stays the books.** The app keeps the sales side and hands GnuCash balanced entries to import.
