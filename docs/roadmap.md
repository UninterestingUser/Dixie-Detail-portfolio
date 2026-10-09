# Roadmap

Eight phases. Each becomes a GitHub milestone, and each task below becomes an issue. A phase is done when its test passes.

## Phase 0: Foundations

- [ ] Server joins the tailnet as its own node ([setup/server.md](setup/server.md))
- [ ] APC USB connected and `apcupsd` installed
- [ ] Docker Compose stack: PostgreSQL, core app, reverse proxy, Cloudflare Tunnel
- [ ] Nightly database dumps to `/mnt/raid`, encrypted off-site copy
- [ ] Control app published to the tailnet with `tailscale serve`
- [ ] Outside uptime monitor
- [ ] Setmore export received

**Done when:** a backup has been restored successfully and the server answers through the tunnel.

## Phase 1: Core data and control app

- [ ] Data model for all nine areas: customers, appointments, pricebook, billing, history, promotions, staff, bookkeeping, marketing
- [ ] Pricebook loaded from `data/price-matrix.csv`, with the maintenance and condition rules
- [ ] Screens for customers, vehicles, pricebook and appointments
- [ ] Setmore history imported
- [ ] Change history on every price and description

**Done when:** the pricebook matches the price matrix cell for cell and the Setmore history is searchable.

## Phase 2: Vehicle catalog

- [ ] EPA and NHTSA import
- [ ] Class rules and owner overrides
- [ ] Size-variant flags: doors, cab, seat rows
- [ ] Review queue and monthly refresh

**Done when:** the owner approves the class and size for every model in the Setmore history and for a spot-check list of common vehicles.

## Phase 3: Scheduling and website

- [ ] Availability engine with the booking rules in [scheduling.md](scheduling.md)
- [ ] Google Workspace calendar sync
- [ ] Sales tax by service address
- [ ] Booking API
- [ ] Homepage and booking-flow mockups approved
- [ ] Astro site with the estimate card, on a staging address
- [ ] Carrier registration submitted once the booking form is public

**Done when:** the owner completes test bookings on the phone, the estimates match the owner's own math, and the design is approved.

## Phase 4: Texts, alerts and payments

- [ ] Quo messages: confirmation, reminder, on my way, payment link, receipt, review request, follow-up
- [ ] STOP, HELP and START handling
- [ ] Time-to-leave alerts
- [ ] Stripe payment links, Cash App Pay and Tap to Pay matching
- [ ] "Paid" buttons for cash, Venmo, PayPal and Bitcoin
- [ ] Invoices and receipts

**Done when:** one test appointment runs from booking through reminder, payment by every method and review request.

## Phase 5: Launch

- [ ] Address-for-address redirects from the WordPress site
- [ ] DNS cutover and Search Console check
- [ ] Number ported to Quo
- [ ] Setmore retired

**Done when:** old links redirect, a real customer books, and Setmore is switched off.

## Phase 6: Back office

- [ ] GnuCash export
- [ ] Sales tax reports by period and jurisdiction
- [ ] Promotions
- [ ] Marketing campaigns
- [ ] Staff records and pay

**Done when:** a month's export imports cleanly into GnuCash and matches the bank deposits.

## Phase 7: Bitcoin

- [ ] BTCPay Server on the home server
- [ ] Lightning decision
- [ ] Automatic Bitcoin invoices

**Done when:** a test Bitcoin invoice marks its appointment paid.
