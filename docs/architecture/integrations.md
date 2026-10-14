---
title: Outside services and integrations
summary: Every outside service the system uses or will use, what it does for the business, which phase connects it, and how it talks to the core app.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [integrations, services]
related: [data/integrations.yaml, data/configuration.yaml, docs/overview/running-costs.md]
---

# Outside services and integrations

Every outside service connects to the core app, never straight to the database. The structured list, with status and phase, is in [data/integrations.yaml](../../data/integrations.yaml); this page explains how each one fits.

## In use since Phase 0

- **Cloudflare.** Runs DNS for `dixiedetail.com` on the free plan and hosts the Tunnel that carries public requests to the server. In Phase 3 it also hosts the website on Cloudflare Pages.
- **Tailscale.** The owner's private network. Every staff device and the server are nodes; pfSense also advertises the home network. The control app is published to the tailnet only.
- **Bitwarden Secrets Manager.** Holds every secret. See [secrets.md](secrets.md).
- **GitHub.** Hosts the private repository. The server pulls with a read-only deploy key.
- **Google Workspace (Drive).** Holds the encrypted off-site backups, through rclone with access only to the files it creates.
- **Healthchecks.io.** Emails the owner when the backup or the public path stops checking in.

## Connected in later phases

- **EPA FuelEconomy.gov and NHTSA vPIC (Phase 2).** Free government vehicle data: year, make and model menus, EPA size classes, and the heavy trucks the EPA leaves out. See [../reference/vehicle-classification.md](../reference/vehicle-classification.md). RockAuto is not used: it has no public API and scraping it may breach its terms.
- **Google Workspace calendars (Phase 3).** Two calendars, Jobs and Time Off, shared with a Google service account: edit on Jobs, read on Time Off. The service account's JSON key is the Bitwarden secret `GOOGLE_SERVICE_ACCOUNT_JSON`, read into memory; there is no key file on disk. Workspace may need one admin setting changed to allow sharing with the service account. See [../reference/scheduling-and-calendars.md](../reference/scheduling-and-calendars.md).
- **Google Maps Platform (Phase 3).** Address suggestions on the booking form (Places Autocomplete) and traffic-aware drive times (Routes). Usage is expected to stay inside the free monthly allowance. The billing account is approved; it must sit on the same Google Cloud project as the calendar service account.
- **Census Bureau geocoder and Tennessee Department of Revenue (Phase 3).** Turn a service address into coordinates and then into a tax jurisdiction and rate. See [../reference/sales-tax.md](../reference/sales-tax.md).
- **Quo, formerly OpenPhone (Phases 3 to 5).** One business number for calls, the owner's own texts and the automated texts, with an Android app. The core app sends through Quo's API and receives replies by webhook. The account is open on a new number on the Starter plan, which includes the API and webhooks. Carrier registration and the port of (423) 380-9120 wait for the new booking form. See [../reference/text-messages.md](../reference/text-messages.md).
- **Stripe (Phase 4).** Card payment links, Cash App Pay inside those links, and Tap to Pay on the Pixel through the Stripe Dashboard app. Links report back by webhook; Tap to Pay payments are matched by amount and time, then confirmed with one tap. See [../reference/payments.md](../reference/payments.md).
- **GnuCash (Phase 6).** The owner's books, fed by a CSV export the owner imports. See [../reference/bookkeeping-gnucash.md](../reference/bookkeeping-gnucash.md).
- **BTCPay Server (Phase 7).** Self-hosted Bitcoin invoices on the home server; the Lightning decision is made then.

## Services considered and not used

| Service | Why not |
| --- | --- |
| Directus or another off-the-shelf admin | Starts faster, but pricing rules, availability and promotions need custom code either way |
| Twilio | Cheaper pure API, but no phone app, so calls would need a second service |
| UptimeRobot | Free plan is non-commercial since October 2024 |
| Backblaze B2 | Google Drive storage is already paid for |
| RockAuto | No public API; scraping may breach its terms |
