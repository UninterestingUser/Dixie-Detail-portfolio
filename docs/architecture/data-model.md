---
title: Data model outline
summary: The business records the database will hold across all nine areas, and how they relate, as designed before Phase 1 builds them.
audience: [owner, developer]
visibility: internal
status: planned
updated: 2026-10-13
tags: [data-model, database, phase-1]
related: [docs/overview/roadmap.md, docs/reference/pricing.md, docs/reference/pricebook-changes.md, docs/reference/returning-customers.md]
---

# Data model outline

This is the design intent for the Phase 1 data model. When Phase 1 builds the real models, this page will be rewritten from the code and its status changed to `current`. Until then, nothing here exists in the database.

The model will cover all nine business areas from the start (customers, appointments, pricebook, billing, history, promotions, staff, bookkeeping, marketing), so later phases add screens without restructuring stored data.

## Customers and vehicles

- **Customer** will hold a name, company if any, mobile number (10 digits, stored without formatting), email, addresses, notes and where the customer came from.
- **Second contact** will hold another person's own name and number on a customer's record. A booking under that number matches the customer. See [../reference/returning-customers.md](../reference/returning-customers.md).
- **Address** will hold a verified service address with its coordinates and tax jurisdiction, and a flag for an approved out-of-area address.
- **Vehicle** will belong to a customer and point to a vehicle model, with year, colour and notes. Vehicles with missing details will be kept and flagged.
- **Vehicle model** will hold make, model and years, the vehicle class, the size-variant rule (doors, cab, or seat rows of 2, 3 or "ask") and its source (EPA, NHTSA, owner override).
- **Consent record** will hold each text consent: kind (appointment or follow-up), date, source (web form or phone) and the wording version. See [../reference/text-messages.md](../reference/text-messages.md).

## Pricebook

- **Service** will hold the service name, description, whether it is an add-on, who can book it, and whether the condition adjustment applies.
- **Price** will hold the price and one-person hours for a service, vehicle class and size variant.
- **Pricing rules** will hold the condition levels, maintenance percentages, crew time factor, rounding and the full-day threshold. Seed values are in [data/pricing-rules.yaml](../../data/pricing-rules.yaml).
- **Pricebook version** will hold a numbered, published state of the pricebook with its effective date and the decisions made for affected bookings. See [../reference/pricebook-changes.md](../reference/pricebook-changes.md).
- **Promotion** will hold a percent or dollar discount, date window, promo code and website banner.

## Appointments and scheduling

- **Appointment** will hold the customer, vehicle, service address, date, arrival time, crew, status (requested, booked, completed, cancelled), preferred payment method and calculated job length.
- **Appointment line** will be the snapshot of each priced line as booked: service, price, hours, condition, promotion, on-site adjustment with reason.
- **Recurring series** will tie repeating Monthly or Quarterly Maintenance visits together.
- **Day closure** will hold Sundays, holidays and days off, including those read from the Time Off calendar.
- **Calendar sync record** will link an appointment to its Jobs calendar event.

## Billing and bookkeeping

- **Invoice** will hold the lines, taxable amount, state tax, local tax, jurisdiction and total.
- **Payment** will hold the method, amount, tip, date, processor reference and fee.
- **Refund** will hold the amount, tax refunded and reason.
- **Tax rate** will hold each jurisdiction's rate with the dates it applies.
- **Export batch** will record each GnuCash export and the transactions in it.

## Staff, messages and marketing

- **Staff member** will hold a login, role, starting point for drive times and pay terms.
- **Assignment** will link staff to appointments.
- **Message** will log every text sent and received, with its template and delivery status.
- **Message template** will hold editable text for each automated message. Seed wording is in [data/message-templates.yaml](../../data/message-templates.yaml).
- **Campaign** will group follow-up messages sent to a chosen set of customers with follow-up consent.

## Cross-cutting

- **Change history** will record who changed every price or description, when, and the old value, so changes can be undone.
- **Settings** will hold hours, booking rules, home base, buffers and the tax sourcing rule. Seed values are in `data/`.
