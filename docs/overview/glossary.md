---
title: Glossary
summary: The exact meaning of every business and technical term used in the Dixie Detail documentation, so people and AI use each word one way.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-14
tags: [glossary, terms]
related: [docs/reference/pricing.md, docs/architecture/system-overview.md]
---

# Glossary

Terms are grouped by subject and listed alphabetically within each group. Use these words exactly; do not swap in synonyms.

## Services and pricing terms

**Add-on.** A service that can only be added to another service: Carpet Extraction and Seat Extraction. Add-ons are priced by seat rows alone and are not affected by the condition level.

**Condition level.** The customer's choice of how dirty the vehicle is, in three levels that add 0%, 10% or 20% to the base price of Full Detail, Interior Only or Exterior Only. The adjustment is rounded to the whole dollar. See [../reference/pricing.md](../reference/pricing.md).

**Derived price rule.** A pricebook rule that prices one service as a percentage of another for the same vehicle class and size variant, with its hours. Quarterly Maintenance at 80% and Monthly Maintenance at 50% of Full Detail are derived price rules.

**Estimate.** The price shown before the job, built from the pricebook. The final price is confirmed on site.

**Full day flag.** A job of 8 or more one-person hours. The control app flags it for a second person, and the customer's estimate card says "full day" instead of hours.

**Line.** One priced item on an appointment: the service, the condition adjustment, each add-on, a promotion, an on-site adjustment, a no-charge line or a custom line.

**Line snapshot.** The copy of each line (service, price, hours, condition, promotion) stored on an appointment when it is booked, so later pricebook changes cannot alter it. See [../reference/pricebook-changes.md](../reference/pricebook-changes.md).

**Maintenance plan.** Monthly Maintenance or Quarterly Maintenance, priced at 50% or 80% of the Full Detail price and booked only by the owner.

**Misc Services.** An owner-only custom line for a one-off job, at a price the owner sets.

**No-charge line.** A line, with a reason, that brings a job's total to zero when the owner gives the job as a gift. A no-charge job has no payment.

**One-person hours.** The job length in the price matrix, measured for one person working alone.

**On-site adjustment.** A price change the owner enters at the job, always with a reason, which appears on the invoice.

**Price matrix.** The owner's table of 90 prices and job lengths, stored in [data/price-matrix.csv](../../data/price-matrix.csv). It is the only source of prices.

**Pricebook.** The price matrix plus its rules (condition levels, maintenance percentages, add-ons, promotions) as stored in the database and edited in the control app.

**Pricebook draft.** A pricebook version still being edited. Once published, a version and its prices never change; the next change is a new draft.

**Pricebook version.** A numbered, published state of the pricebook with an effective date.

**Promotion.** A named offer, such as Friends & Family, Multi-Vehicle or a seasonal offer, defined as a percentage off, a dollar amount off or a fixed price. It appears on a job as its own line.

**Size variant.** The 1, 2 or 3 in the price matrix's size column, also called "seat rows". What it measures depends on the vehicle class: doors for cars, cab style for pickups, seat rows for crossovers and SUVs.

**Vehicle class.** One of six groups that set the price: Coupes & Sedans; Crossovers & Wagons; Light Pickups & Offroad; Midsize SUVs; Fullsize SUVs & Minivans; Fullsize Trucks. See [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml).

## Booking and scheduling terms

**Arrival time.** The time the crew arrives: 8:00, 8:30 or 9:00 AM.

**Booking flow.** The seven-step process on the website that ends in a confirmed appointment. See [../reference/booking-flow.md](../reference/booking-flow.md).

**Crew.** The one or two people working a job. Two people take 60% of the one-person hours.

**Estimate card.** The running total shown beside the booking steps on a desktop, and as a bar at the bottom of a phone screen.

**Home base.** The address drive times start from, normally the owner's home. A setting.

**Jobs calendar.** The Google calendar "Dixie Detail Jobs", written only by the system.

**Time Off calendar.** The Google calendar "Dixie Detail Time Off", written by the owner. An all-day event closes that day for booking.

**Time-to-leave alert.** A push notification sent at drive time plus 10 minutes before a job's start.

## Customer terms

**Approved out-of-area address.** An address outside the five counties that the owner has allowed to book. It is charged no Tennessee sales tax.

**Consent.** A customer's recorded permission to receive texts, of two separate kinds: appointment texts and follow-up texts. See [../reference/text-messages.md](../reference/text-messages.md).

**Match flag.** A difference in name, address or vehicle between a booking and the customer it was quietly matched to, waiting for the owner to choose one of four actions. See [../reference/returning-customers.md](../reference/returning-customers.md).

**Quiet matching.** Linking a new booking to an existing customer by mobile number, without showing the customer anything. See [../reference/returning-customers.md](../reference/returning-customers.md).

**Second contact.** A second person with their own name and number on a customer's record, such as a spouse, who can book under that record.

**Service address.** The address where the job is done. It sets the sales tax rate and the drive time.

## Money and bookkeeping terms

**Check.** A payment by paper check, an owner-only payment method. It posts to the business checking account in GnuCash.

**Jurisdiction.** The city or county whose local sales tax rate applies to a service address.

**Multi-split CSV.** The GnuCash import format the system exports: a row with a date starts a transaction, and the rows below it are its other splits. See [../reference/bookkeeping-gnucash.md](../reference/bookkeeping-gnucash.md).

**Negative tip.** How a short payment is recorded: when a customer pays less than the total, the shortfall is a tip below zero, and the job's lines keep the full price.

**Owner-only payment method.** Check or trade: accepted by the owner case by case and never offered on the website. See [../reference/payments.md](../reference/payments.md).

**"Paid" button.** The one-tap control the owner uses to mark cash, Venmo, PayPal and Bitcoin payments as received.

**Prepayment.** A payment recorded before the job, such as a gift card, so the appointment shows as already paid.

**Sales Tax Payable.** The GnuCash liability account that holds collected sales tax until it is remitted.

**Split payment.** A job paid with two methods, recorded as one payment for each method.

**Trade.** A job paid in goods instead of money, an owner-only payment method. The goods and their value are recorded; the value is the payment amount. Trades are left out of the GnuCash export and entered by hand.

## Staff terms

**Assignment.** A staff member on a job, with the flat pay for that job.

**Helper.** A person other than the owner who works jobs, such as a family member, paid a flat amount per job.

**Helper pay.** The flat amount a helper earns per job. Each helper has a usual amount, copied onto each assignment, which the owner can override for one job. It posts to the Professional Services expense account in GnuCash.

**Staff payout.** Money paid to a helper that settles one or more assignments.

## System terms

**Baserow id.** The id of the Baserow row an imported customer, vehicle or appointment came from. It is kept so the import can be re-run before launch without making duplicates.

**Change history.** The earlier versions of a record, with who changed it and when, kept for the pricebook (promotions included), customers, vehicles and appointments.

**Control app.** The private web app the owner and staff use to run the business, served by the core app and reachable only over Tailscale.

**Core app.** The Django application on the home server that holds the business logic, the REST API, the control app and the scheduled jobs.

**Deploy key.** A read-only GitHub key that lets the server pull the repository. It is stored in Bitwarden and loaded only for a pull.

**Healthchecks check.** A monitor on Healthchecks.io that emails the owner when the server stops checking in.

**Machine account.** The Bitwarden Secrets Manager identity the server uses to read secrets. Its access token is the one secret the server stores, encrypted.

**Private door.** The control app's entrance: Caddy on 127.0.0.1:8000, published to the tailnet with `tailscale serve`.

**Public API.** The three things the internet can ask the core app: list services and prices, show open slots, take a booking.

**Public door.** Caddy's port 8080 inside the Docker network, reached only by the Cloudflare Tunnel, answering only `/health` and `/api/public/`.

**Restic snapshot.** One encrypted backup stored in Google Drive by restic.

**Tailnet.** The owner's private Tailscale network, which every staff device joins.

**Tunnel.** The Cloudflare Tunnel: an outbound-only connection from the server to Cloudflare that carries public requests in without opening a port.
