---
title: Outside services and integrations
summary: Every outside service the system uses or will use, what it does for the business, which phase connects it, and how it talks to the core app.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-19
tags: [integrations, services]
related: [data/integrations.yaml, data/configuration.yaml, docs/overview/running-costs.md]
---

# Outside services and integrations

Every outside service connects to the core app, never straight to the database. The structured list, with status and phase, is in [data/integrations.yaml](../../data/integrations.yaml); this page explains how each one fits.

## In use since Phase 0

- **Cloudflare.** Runs DNS for `dixiedetail.com` on the free plan and hosts the Tunnel that carries public requests to the server. Since Phase 3 it also hosts the website and runs Turnstile; see below.
- **Tailscale.** The owner's private network. Every staff device and the server are nodes; pfSense also advertises the home network. The control app is published to the tailnet only.
- **Bitwarden Secrets Manager.** Holds every secret. See [secrets.md](secrets.md).
- **GitHub.** Hosts the private repository. The server pulls with a read-only deploy key.
- **Google Workspace (Drive).** Held the encrypted off-site backups, through rclone, until 2026-11. Retired by decision 0127: its history was copied to the backup server, and Backblaze B2 holds the off-site copy.
- **Healthchecks.io.** Emails the owner when the backup, the public path, the monthly vehicle data refresh, the morning sales tax rate check or the nightly calendar check stops checking in or fails ([../operations/monitoring.md](../operations/monitoring.md)).

## In use since the review of 2026-11

- **Backblaze B2.** Holds the nightly off-site copy of the backups: a private bucket reached through restic's S3-compatible backend, with a key that can reach only that bucket. Nothing but restic's encrypted repository is stored there, and a weekly check lists the bucket to prove it. Prior versions are kept 30 days ([decision 0127](../decisions/0127-hourly-backups-to-the-backup-host-and-nightly-to-backblaze.md)).

## In use since Phase 2

- **EPA FuelEconomy.gov and NHTSA vPIC.** Free government vehicle data: year, make and model menus, EPA size classes, the heavy trucks the EPA leaves out, motorcycle models, and, from vPIC's Canadian vehicle specifications, curb weight and dimensions per trim for the classification rules. The `import_vehicle_data` command loads them into the vehicle catalog, caching each download and pausing between vPIC calls, and `dixie-vehicle-refresh.timer` refreshes them on the first Sunday of each month at 4:15 AM Eastern; see [../reference/vehicle-catalog.md](../reference/vehicle-catalog.md) and [../reference/vehicle-classification.md](../reference/vehicle-classification.md). RockAuto is not used: it has no public API and scraping it may breach its terms.

## In use since Phase 3

- **Google Workspace calendars.** Two calendars, Jobs and Time Off, shared with a Google service account: edit on Jobs, read on Time Off. The service account's JSON key is the Bitwarden secret `GOOGLE_SERVICE_ACCOUNT_JSON`, read into memory; there is no key file on disk. Workspace needs one admin setting changed to allow sharing with the service account. The sync has worked since Phase 3, Step 3: a queue in PostgreSQL, the calendar worker container, and a nightly check that pings Healthchecks ([decision 0098](../decisions/0098-calendar-sync-queue-and-worker.md)). The key is handed to the containers as a file on an in-memory mount. See [../reference/scheduling-and-calendars.md](../reference/scheduling-and-calendars.md); how it was connected is in [../operations/connecting-the-google-calendars.md](../operations/connecting-the-google-calendars.md).
- **Google Maps Platform.** Address suggestions on the booking form (Places Autocomplete, in the customer's browser with the public browser key), the server's own lookup of the address picked (Place Details, asking only for Essentials fields), a search for a typed address the Census geocoder cannot find (Text Search, place IDs only, used only if it agrees with the typed address; [decision 0092](../decisions/0092-google-fallback-and-locations-set-by-hand.md)) and traffic-aware drive times (Routes), cached by address pair and hour. Every server call is counted and capped per day below the limits set in Google Cloud, and a drive time falls back to a marked estimate when Google can't be asked ([decision 0091](../decisions/0091-google-calls-counted-capped-and-cached.md)). The homepage's service area map uses the Maps Embed API in view mode with the same browser key; it has no charge and loads only as the visitor scrolls near it. The billing account sits on the same Google Cloud project as the calendar service account. It is on Google's free trial until about 2027-02-03, which locks the daily quotas, so the account is upgraded and the daily limits set by 2027-01-15 (an owner action in [../overview/roadmap.md](../overview/roadmap.md#owner-actions-still-open)).
- **Census Bureau geocoder and Tennessee Department of Revenue.** The geocoder gives the coordinates and county of an address the owner types. The Department of Revenue's map service gives the rate boundaries and local rates, loaded by `import_tax_rates` and checked every morning; the server matches each address to its jurisdiction itself. See [../reference/sales-tax.md](../reference/sales-tax.md) and [decision 0090](../decisions/0090-tax-rates-from-the-state-boundaries.md).
- **Cloudflare Pages, Workers and Workers KV.** The Astro website in `site/` is built and hosted on Cloudflare Pages, on its staging address until the Phase 5 launch. The deploy hook, the Bitwarden secret `CLOUDFLARE_PAGES_DEPLOY_HOOK`, rebuilds it when a pricebook version is published or takes effect and when reviews change. While the server or Google can't be reached, a Pages Function takes the request a time form into a Workers KV namespace, and the offline-replay Worker sends each request to the public API every 5 minutes until it answers ([decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md), [../guides/previewing-and-deploying-the-website.md](../guides/previewing-and-deploying-the-website.md)).
- **Cloudflare Turnstile.** Free; checks that bookings, quote requests and photo upload sessions come from a person. The site key is public, in the site's build settings; the server checks each token with the secret key `TURNSTILE_SECRET_KEY` ([../reference/public-api.md](../reference/public-api.md)).

## Connected in later phases

- **Quo, formerly OpenPhone (Phases 4 and 5).** One business number for calls, the owner's own texts and the automated texts, with an Android app. The core app sends through Quo's API and receives replies by webhook. The account is open on a new number on the Starter plan, which includes the API and webhooks. Carrier registration can start now that the booking form with its consent checkbox is on the staging site; the port of (423) 380-9120 waits for its approval. See [../reference/text-messages.md](../reference/text-messages.md).
- **Stripe (Phase 4).** Card payment links, Cash App Pay inside those links, and Tap to Pay on the Pixel through the Stripe Dashboard app. Links report back by webhook; Tap to Pay payments are matched by amount and time, then confirmed with one tap. See [../reference/payments.md](../reference/payments.md).
- **GnuCash (Phase 6).** The owner's books, fed by a CSV export the owner imports. See [../reference/bookkeeping-gnucash.md](../reference/bookkeeping-gnucash.md).
- **BTCPay Server (Phase 7).** Self-hosted Bitcoin invoices on the home server; the Lightning decision is made then.

## Services considered and not used

| Service | Why not |
| --- | --- |
| Directus or another off-the-shelf admin | Starts faster, but pricing rules, availability and promotions need custom code either way |
| Twilio | Cheaper pure API, but no phone app, so calls would need a second service |
| UptimeRobot | Free plan is non-commercial since October 2024 |
| RockAuto | No public API; scraping may breach its terms |
