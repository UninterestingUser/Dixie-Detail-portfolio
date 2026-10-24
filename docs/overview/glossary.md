---
title: Glossary
summary: The exact meaning of every business and technical term used in the Dixie Detail documentation, so people and AI use each word one way.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-24
tags: [glossary, terms]
related: [docs/reference/pricing.md, docs/architecture/system-overview.md]
---

# Glossary

Terms are grouped by subject and listed alphabetically within each group. Use these words exactly; do not swap in synonyms.

## Services and pricing terms

**Add-on.** A service that can only be added to another service: Carpet Extraction and Seat Extraction. Add-ons are priced by seat rows alone and are not affected by the condition level.

**Condition level.** The customer's choice of how dirty the vehicle is, in three levels that add 0%, 10% or 20% to the base price and the service time of Full Detail, Interior Only or Exterior Only. The price adjustment is rounded to the whole dollar; the extra time is not rounded until the job's service time is. See [../reference/pricing.md](../reference/pricing.md).

**Derived price rule.** A pricebook rule that prices one service as a percentage of another for the same vehicle class and size variant, with its hours. Quarterly Maintenance at 80% and Monthly Maintenance at 50% of Full Detail are derived price rules.

**Estimate.** The price shown before the job, built from the pricebook. The final price is confirmed on site.

**Full day flag.** A job whose one-person time on site is 8 hours or more (7 or more one-person service hours). The control app flags it for a second person, and the customer's estimate card says "full day" instead of hours.

**Line.** One priced item on an appointment: the service, the condition adjustment, each add-on, a promotion, an on-site adjustment, a no-charge line or a custom line.

**Line snapshot.** The copy of each line (service, price, hours, condition, promotion) stored on an appointment when it is booked, so later pricebook changes cannot alter it. See [../reference/pricebook-changes.md](../reference/pricebook-changes.md).

**Maintenance plan.** Monthly Maintenance or Quarterly Maintenance, priced at 50% or 80% of the Full Detail price and booked only by the owner.

**Misc Services.** An owner-only custom line for a one-off job, at a price the owner sets.

**No-charge line.** A line, with a reason, that brings a job's total to zero when the owner gives the job as a gift. A no-charge job has no payment.

**One-person service hours.** The service time in the price matrix, measured for one person working alone. Setup and breakdown are not included. Called "one-person hours" before 2026-10-17, when the hours still included them.

**On-site adjustment.** A price change the owner enters at the job, always with a reason, which appears on the invoice.

**Price basis.** How a vehicle class is priced. Every class uses the fixed price list, the only basis built; another, such as per foot of length, could be added for a class later.

**Price matrix.** The owner's table of 90 prices and one-person service hours, stored in [data/price-matrix.csv](../../data/price-matrix.csv). It is the only source of prices.

**Pricebook.** The price matrix plus its rules (condition levels, maintenance percentages, add-ons, promotions) as stored in the database and edited in the control app.

**Pricebook draft.** A pricebook version still being edited. Once published, a version and its prices never change; the next change is a new draft.

**Pricebook version.** A numbered, published state of the pricebook with an effective date.

**Pricing engine.** The one module on the server that works out every price, line and service time from the pricebook. Nothing else does price arithmetic.

**Promotion.** A named offer, such as Friends & Family, Multi-Vehicle or a seasonal offer, defined as a percentage off, a dollar amount off or a fixed price. It appears on a job as its own line.

**Quote.** The server's record of a priced job before booking: its inputs, lines, totals, pricebook version, tax rate, service time and time on site. It never changes once issued. A booking refers to the quote, and its lines become the appointment's line snapshot. See [../reference/pricing.md](../reference/pricing.md).

**Service time.** The time spent working on the vehicle, without setup and breakdown. The price matrix holds one-person service time; two people take 60% of it, rounded to the nearest 15 minutes. The pricing engine returns service time.

**Size variant.** One size within a vehicle class, numbered in the price matrix's size column (1, 2 or 3 at launch) and also called "seat rows". What it measures depends on the vehicle class: doors for cars, cab style for pickups, seat rows for crossovers and SUVs. A class can have none, such as Motorcycles, and then has a single price per service.

**Voucher.** A free promotional offer with a code and a dollar value. It is a kind of promotion and appears on a job as a promotion line.

**Vehicle class.** A group of vehicles that share prices. There are seven at launch: Coupes & Sedans; Crossovers & Wagons; Light Pickups & Offroad; Midsize SUVs; Fullsize SUVs & Minivans; Fullsize Trucks; Motorcycles. Classes are records the owner can add, rename or retire without a code change; a retired class stays for history. See [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml).

**Vehicle model.** A make and model a customer picks, such as Toyota RAV4, over a range of model years. A vehicle class applies to a vehicle model. Its vehicle type is "car, truck or van" or "motorcycle"; motorcycles are in the same year, make and model lists, labeled, and in the Motorcycles class. Each of its model years gets a vehicle class from the classification rules. See [../reference/vehicle-catalog.md](../reference/vehicle-catalog.md).

**Classification rule.** One rule of the ordered list that gives a model year its vehicle class: conditions on stored facts, such as "EPA small SUV weighing over 4,500 lb", and the class it gives. The first rule whose conditions all hold wins. See [../reference/vehicle-classification.md](../reference/vehicle-classification.md).

**Model override.** The owner's vehicle class for a vehicle model, or some of its years, which beats every rule, such as Jeep Wrangler to Light Pickups & Offroad. A **vehicle override** is the same for one customer's vehicle, such as a lifted truck, and beats both.

**Nameplate.** A vehicle customers know by its own name, such as the Santa Fe Sport, that the EPA files under another base model, such as the Santa Fe. The catalog splits these out with [data/vehicle-names.yaml](../../data/vehicle-names.yaml), which also lists the other spellings of one vehicle, such as "GLE-Class" for the GLE.

**Photo card.** One card per vehicle class, with a picture and caption, that a customer picks from when their vehicle is not in the catalog, such as a pre-1984 classic. There are seven.

**Approval list.** The control app's **Approvals** screen, where the owner approves the class of each year range of every model in the job history, the spot-check list in [data/approval-spot-checks.yaml](../../data/approval-spot-checks.yaml) and every model whose years are in different classes. A later change that alters an approved range clears its approval (decision 0079).

**Differences screen.** The control app's **Differences** screen, listing each customer's vehicle whose own class or size differs from the catalog's, with three choices: keep the imported class as the vehicle's own override, take the catalog's, or give every vehicle of the model that class (decision 0077).

**Customer alias.** A customer's name for a vehicle the catalog files under another name or make, such as "Chevrolet 2500" for the Silverado HD, in [data/vehicle-names.yaml](../../data/vehicle-names.yaml). It may hold only for some model years, as a "Dodge Ram" is the Ram 1500 only from 2011 (decision 0080).

**Trim words.** The words, such as "LE", "XLT" or "Crew Cab", that `link_vehicles` may leave off the end of a customer's model name when it links the vehicle to the catalog, listed in [data/vehicle-names.yaml](../../data/vehicle-names.yaml).

**Review queue (vehicles).** The model years no classification rule settles cleanly, waiting for the owner: no rule matches, the trims straddle a rule's threshold, or two sources disagree. They do not go live until the owner settles them: a **review queue decision** (accept the suggested class, pick another, or send it to the photo cards), a rule or a model override. Not the same as the returning-customer match flags.

**Third-row list.** [data/third-row-seating.yaml](../../data/third-row-seating.yaml), the owner-approved list of which crossovers and midsize SUVs have a third row always, optionally or never, by model year. Optional is asked in the booking form.

## Booking and scheduling terms

**Arrival time.** The time the crew arrives and setup starts. It is the start time the customer picks.

**Booking flow.** The seven-step process on the website that ends in a confirmed appointment. See [../reference/booking-flow.md](../reference/booking-flow.md).

**Breakdown time.** The time after the service to pack up, 30 minutes for one person divided by the number of people on the job. A scheduling setting.

**Crew.** The one or two people working a job. Two people take 60% of the one-person service time, and split setup and breakdown between them.

**Estimate card.** The running total shown beside the booking steps on a desktop, and as a bar at the bottom of a phone screen.

**Home base.** The address drive times start from, normally the owner's home. A setting.

**Jobs calendar.** The Google calendar "Dixie Detail Jobs", written only by the system. An edit made to it in Google is reset at the next sync.

**Scheduling setting.** One of the rules that decide which days and start times are open, such as working hours, minimum notice or jobs per day. Launch values are in [data/booking-rules.yaml](../../data/booking-rules.yaml); live values will be in the database. See [../reference/scheduling-and-calendars.md](../reference/scheduling-and-calendars.md).

**Setup time.** The time before the service to unpack and get ready, 30 minutes for one person divided by the number of people on the job. A scheduling setting.

**Start time.** A time a job can begin, offered online from that weekday's list of start times (8:00, 8:30 and 9:00 AM at launch). The start time is the arrival time.

**Time Off calendar.** The Google calendar "Dixie Detail Time Off", written by the owner. An all-day event closes that day for booking; a timed event blocks only its own time.

**Time on site.** How long the crew is at the customer's address: setup + service time + breakdown, rounded to the nearest 15 minutes. The Jobs calendar event and the estimate card show time on site.

**Time-to-leave alert.** A push notification sent at drive time plus 10 minutes before a job's arrival time.

## Customer terms

**Approved out-of-area address.** An address outside the five counties that the owner has allowed to book. It is charged no Tennessee sales tax.

**Consent.** A customer's recorded permission to receive texts, of two separate kinds: appointment texts and follow-up texts. See [../reference/text-messages.md](../reference/text-messages.md).

**Match flag.** A difference in name, address or vehicle between a booking and the customer it was quietly matched to, waiting for the owner to choose one of four actions. See [../reference/returning-customers.md](../reference/returning-customers.md).

**Quiet matching.** Linking a new booking to an existing customer by mobile number, without showing the customer anything. See [../reference/returning-customers.md](../reference/returning-customers.md).

**Second contact.** A second person with their own name and number on a customer's record, such as a spouse, who can book under that record.

**Service address.** The address where the job is done. It sets the sales tax rate and the drive time.

## Money and bookkeeping terms

**Check.** A payment by paper check, an owner-only payment method. It posts to the business checking account in GnuCash.

**Gift card.** A dollar balance sold in advance, with sales tax included, identified by a code and recording the buyer and any recipient. The balance is money owed until it is used, can be spent across several jobs, and never goes below zero. See [../reference/payments.md](../reference/payments.md).

**Jurisdiction.** The city or county whose local sales tax rate applies to a service address.

**Multi-split CSV.** The GnuCash import format the system exports: a row with a date starts a transaction, and the rows below it are its other splits. See [../reference/bookkeeping-gnucash.md](../reference/bookkeeping-gnucash.md).

**Negative tip.** How a short payment is recorded: when a customer pays less than the total, the shortfall is a tip below zero, and the job's lines keep the full price.

**Owner-only payment method.** Check or trade: accepted by the owner case by case and never offered on the website. See [../reference/payments.md](../reference/payments.md).

**"Paid" button.** The one-tap control the owner uses to mark cash, Venmo, PayPal and Bitcoin payments as received.

**Prepayment.** A payment recorded before the job, so the appointment shows as already paid. The one imported gift-card job is a prepayment.

**Sales Tax Payable.** The GnuCash liability account that holds collected sales tax until it is remitted.

**Split payment.** A job paid with two methods, recorded as one payment for each method.

**Trade.** A job paid in goods instead of money, an owner-only payment method. The goods and their value are recorded; the value is the payment amount. Trades are left out of the GnuCash export and entered by hand.

## Staff terms

**Assignment.** A staff member on a job, with the flat pay for that job.

**Authorization.** The record that a staff member may perform a service. Managers are authorized for every service. A manager can assign someone not yet authorized, for training, with a reason. See [../reference/control-app.md](../reference/control-app.md).

**Family helper.** A helper who is a member of the owner's family. Family helpers are paid a flat amount per job as professional services, on the owner's accountant's advice; it is the only pay type in use.

**Helper.** A person other than the owner who works jobs, paid a flat amount per job. Each helper has a pay type: family helper or employee (planned).

**Helper pay.** The flat amount a helper earns per job. Each helper has a usual amount, copied onto each assignment, which the owner can override for one job. Its GnuCash account comes from the helper's pay type: Professional Services for a family helper; an employee's wages account is a later decision.

**Manager.** A staff member who can assign staff, book outside the scheduling rules and is authorized for every service. Only the owner today.

**Staff payout.** Money paid to a helper that settles one or more assignments.

## System terms

**Baserow id.** The id of the Baserow row an imported customer, vehicle or appointment came from. It is kept so the import can be re-run before launch without making duplicates.

**Change history.** The earlier versions of a record, with who changed it and when, kept for the pricebook (promotions included), customers, vehicles and appointments.

**Control app.** The private web app the owner and staff use to run the business, served by the core app and reachable only over Tailscale.

**Core app.** The Django application on the home server that holds the business logic, the REST API, the control app and the scheduled jobs.

**Deploy key.** A read-only GitHub key that lets the server pull the repository. It is stored in Bitwarden and loaded only for a pull.

**Healthchecks check.** A monitor on Healthchecks.io that emails the owner when the server stops checking in.

**Machine account.** The Bitwarden Secrets Manager identity the server uses to read secrets. Its access token is the one secret the server stores, encrypted.

**Model-year facts.** One source's facts about one model year of a vehicle model, such as the EPA's size classes and volumes for the 2019 Toyota RAV4, kept as lists and as lowest and highest values across the source's rows. Each source, and the owner, has its own record. See [../reference/vehicle-catalog.md](../reference/vehicle-catalog.md).

**Private door.** The control app's entrance: Caddy on 127.0.0.1:8000, published to the tailnet with `tailscale serve`.

**Public API.** The three things the internet can ask the core app: list services and prices, show open slots, take a booking.

**Public door.** Caddy's port 8080 inside the Docker network, reached only by the Cloudflare Tunnel, answering only `/health` and `/api/public/`.

**Restic snapshot.** One encrypted backup stored in Google Drive by restic.

**Tailnet.** The owner's private Tailscale network, which every staff device joins.

**Tunnel.** The Cloudflare Tunnel: an outbound-only connection from the server to Cloudflare that carries public requests in without opening a port.
