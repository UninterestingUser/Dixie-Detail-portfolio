---
title: Decision records
summary: The index of every settled decision about the Dixie Detail system, with links to the record that explains each one.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-14
tags: [decisions, index]
related: [docs/CONVENTIONS.md, docs/templates/decision-template.md]
---

# Decision records

Each decision has its own file with the context, the decision, the alternatives considered and the consequences. Numbers are permanent identifiers in the order decisions were recorded. A changed decision gets a new record that supersedes the old one; old records are never rewritten. How to add one is in [../CONVENTIONS.md](../CONVENTIONS.md#decision-records).

Records 0001 to 0028 were first kept as rows in a single table (`docs/decisions.md`); they were split into files on 2026-10-13 with their original numbers. Records 0029 to 0044 capture decisions made during planning and Phase 0 that had not yet been written down. Records 0045 to 0052 set the conventions Phase 1 builds on. Records 0053 and 0054 add owner-only payment methods, gift cards and vouchers found in the job history.

## Open points

- **0022:** rounding the second Monthly job's start up to the quarter hour is proposed, not yet confirmed by the owner.
- **0037:** the Georgia tax treatment awaits the accountant's confirmation.

## All decisions

| # | Date | Area | Decision | Status |
| --- | --- | --- | --- | --- |
| [0001](0001-postgresql-and-django.md) | 2026-10-07 | stack | PostgreSQL and Django for the database, API and control app | accepted |
| [0002](0002-astro-on-cloudflare.md) | 2026-10-07 | stack | Astro static website on Cloudflare's free plan | accepted |
| [0003](0003-built-in-scheduling.md) | 2026-10-07 | scheduling | Build scheduling into the core app and retire Setmore | accepted |
| [0004](0004-home-server-hosting.md) | 2026-10-07 | hosting | Business data on the owner's home server | accepted |
| [0005](0005-tailscale-private-access.md) | 2026-10-07 | network | Private access over Tailscale, with the server as its own node | accepted |
| [0006](0006-two-google-calendars.md) | 2026-10-07 | calendar | Two Google Workspace calendars: Jobs and Time Off | accepted |
| [0007](0007-quo-phone-and-texts.md) | 2026-10-07 | phone | Quo for calls and texts, porting the business number after registration | accepted |
| [0008](0008-stripe-and-manual-payments.md) | 2026-10-07 | payments | Stripe for cards and Cash App Pay; a "paid" button for the rest; no deposit | accepted |
| [0009](0009-bitcoin-later-phase.md) | 2026-10-07 | payments | Bitcoin automation moves to its own phase after launch | accepted |
| [0010](0010-gnucash-stays.md) | 2026-10-07 | bookkeeping | GnuCash stays the general ledger, fed by an export | accepted |
| [0011](0011-price-matrix-supersedes-website.md) | 2026-10-07 | pricing | The price matrix supersedes every price on the old website | accepted |
| [0012](0012-maintenance-priced-from-full-detail.md) | 2026-10-07 | pricing | Maintenance plans are priced as a share of Full Detail | accepted |
| [0013](0013-condition-levels.md) | 2026-10-07 | pricing | Three condition levels add 0%, 10% or 20% | accepted |
| [0014](0014-cars-priced-by-doors.md) | 2026-10-07 | pricing | Cars are priced by doors, not seats | accepted |
| [0015](0015-crossover-three-row-price.md) | 2026-10-07 | pricing | Crossovers & Wagons gain a three-row price | accepted |
| [0016](0016-size-from-vehicle-data.md) | 2026-10-07 | booking | Derive the size variant from vehicle data; ask only when needed | accepted |
| [0017](0017-two-person-crew-time.md) | 2026-10-07 | crew | Two people take 60% of the one-person time | accepted |
| [0018](0018-monthly-maintenance-two-person-default.md) | 2026-10-07 | crew | Monthly Maintenance defaults to a two-person crew | accepted |
| [0019](0019-second-person-flag-at-8-hours.md) | 2026-10-07 | crew | Flag a second person at 8 one-person hours | accepted |
| [0020](0020-arrival-times-and-notice.md) | 2026-10-07 | booking | Arrival at 8:00, 8:30 or 9:00 AM, closed Sundays, two days' notice | accepted |
| [0021](0021-one-job-per-day.md) | 2026-10-07 | booking | One job per day, except two Monthly Maintenance jobs | accepted |
| [0022](0022-second-monthly-job-timing.md) | 2026-10-07 | booking | Timing of the second Monthly Maintenance job | accepted |
| [0023](0023-time-to-leave-alert.md) | 2026-10-07 | alerts | Time-to-leave alert at drive time plus 10 minutes | accepted |
| [0024](0024-google-maps-platform.md) | 2026-10-07 | maps | Google Maps Platform for address suggestions and drive times | accepted |
| [0025](0025-sales-tax-by-service-address.md) | 2026-10-07 | tax | Sales tax added on top at the service address's rate | accepted |
| [0026](0026-carrier-registration-timing.md) | 2026-10-08 | texting | Submit text registration when the new booking form is public | accepted |
| [0027](0027-backups-to-google-drive.md) | 2026-10-13 | backups | Nightly backups to the RAID and to Google Drive with restic | accepted |
| [0028](0028-secrets-in-bitwarden.md) | 2026-10-13 | security | Every secret lives in Bitwarden Secrets Manager | accepted |
| [0029](0029-vehicle-data-from-epa-and-nhtsa.md) | 2026-10-07 | vehicles | Vehicle data from EPA FuelEconomy.gov and NHTSA vPIC | accepted |
| [0030](0030-two-text-consents.md) | 2026-10-07 | texting | Two separate text consents: appointment and follow-up | accepted |
| [0031](0031-website-design-direction.md) | 2026-10-10 | website | Website design direction: red base, navy accent, familiar sections kept | accepted |
| [0032](0032-address-validation-with-places.md) | 2026-10-10 | booking | Booking addresses validated with Google Places Autocomplete | accepted |
| [0033](0033-pricebook-versions-and-line-snapshots.md) | 2026-10-11 | pricing | Pricebook versions with line snapshots on every appointment | accepted |
| [0034](0034-quiet-customer-matching.md) | 2026-10-11 | customers | Returning customers matched quietly by phone number | accepted |
| [0035](0035-gnucash-account-mapping.md) | 2026-10-11 | bookkeeping | GnuCash account mapping and booked-when-paid | accepted |
| [0036](0036-baserow-import.md) | 2026-10-11 | migration | One-time import from Baserow, with Setmore filling gaps | accepted |
| [0037](0037-approved-out-of-area-addresses.md) | 2026-10-11 | tax | Approved out-of-area addresses, with no Tennessee tax | accepted |
| [0038](0038-two-doors-access-model.md) | 2026-10-12 | network | Two doors into the app: private over Tailscale, public through the tunnel | accepted |
| [0039](0039-healthchecks-monitoring.md) | 2026-10-12 | monitoring | Healthchecks.io for outside monitoring | accepted |
| [0040](0040-deploy-key-in-bitwarden.md) | 2026-10-12 | security | The server pulls with a read-only deploy key kept in Bitwarden | accepted |
| [0041](0041-backup-password-paper-copy.md) | 2026-10-13 | security | The backup password also has a vault copy and a sealed paper copy | accepted |
| [0042](0042-server-paths.md) | 2026-10-13 | infrastructure | Server paths: code at /srv/dixie-detail, backups at /mnt/raid/Backups/dixie-detail | accepted |
| [0043](0043-workstation-git-over-https.md) | 2026-10-13 | security | Workstation Git over HTTPS with the GitHub CLI keyring | accepted |
| [0044](0044-documentation-as-code.md) | 2026-10-13 | documentation | Documentation lives in the repository as Markdown and YAML | accepted |
| [0045](0045-development-made-up-values.md) | 2026-10-14 | security | Development and tests use made-up throwaway values, not Bitwarden | accepted |
| [0046](0046-control-app-django-htmx.md) | 2026-10-14 | control-app | Control app screens are Django pages with htmx, mobile-first and installable; Django admin for superusers only | accepted |
| [0047](0047-money-as-exact-decimals.md) | 2026-10-14 | pricing | Money is stored as exact decimals, never floating point | accepted |
| [0048](0048-times-utc-shown-eastern.md) | 2026-10-14 | scheduling | Times are stored in UTC and shown in Eastern | accepted |
| [0049](0049-phone-numbers-ten-digits.md) | 2026-10-14 | customers | Phone numbers are stored as 10 digits | accepted |
| [0050](0050-change-history-simple-history.md) | 2026-10-14 | stack | django-simple-history records changes to the pricebook, customers, vehicles and appointments | accepted |
| [0051](0051-baserow-ids-kept-on-import.md) | 2026-10-14 | migration | Imported records keep their Baserow ids so the import can be re-run before launch | accepted |
| [0052](0052-django-sign-in-over-tailscale.md) | 2026-10-14 | security | Django sign-in, reachable only over Tailscale | accepted |
| [0053](0053-check-and-trade-owner-only.md) | 2026-10-14 | payments | Check and trade are owner-only payment methods | accepted |
| [0054](0054-gift-cards-and-vouchers.md) | 2026-10-14 | payments | Gift cards are a balance owed until used; vouchers are promotions | accepted |
