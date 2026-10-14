---
title: Project goals and scope
summary: Why the Dixie Detail business system is being built, what it must achieve, what it deliberately leaves out, and how success is judged.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [goals, scope, overview]
related: [docs/overview/business-profile.md, docs/overview/roadmap.md, docs/architecture/system-overview.md]
---

# Project goals and scope

Dixie Detail LLC is a one-person mobile vehicle detailing business in southeast Tennessee that runs today on a mix of separate tools: a WordPress website, Setmore for online booking, Baserow for customer and job records, and GnuCash for the books. The business system replaces the first three with one system the owner controls, and feeds the fourth.

## The core idea: one database as the source of truth

One PostgreSQL database on the owner's home server holds every customer, vehicle, appointment, price, payment, text message and setting. Everything else reads from it or writes to it through one core application:

- the **public website**, which shows live prices and takes bookings
- the **control app**, a private web app the owner uses to run the business
- the **Google calendars**, which mirror appointments and supply days off
- the **outside services**: Stripe for cards, Quo for texts, Google Maps for drive times and address checks

Nothing is entered twice. A price changed in the control app is the price the website shows, the price the booking flow charges and the price on the invoice.

## Goals

1. **Online booking that ends in a confirmed appointment.** A customer picks a vehicle, sees a running estimate, chooses a date and books, without a phone call. Setmore is retired.
2. **One correct price everywhere.** The owner's price matrix is the only price source, and every price is calculated on the server from it.
3. **Less admin per job.** Confirmations, reminders, "on my way", payment links, receipts and review requests go out automatically, to customers who agreed to texts.
4. **Clean books with no retyping.** Paid jobs export to GnuCash as balanced entries, with sales tax tracked by jurisdiction until it is remitted.
5. **A fast website that keeps its search ranking.** The new static site loads faster than WordPress, keeps every old address working, and stays up when the home server is down.
6. **Owned, private and secure.** The business data stays on the owner's hardware. The control app is never on the public internet, card details never touch the server, and every secret lives in Bitwarden Secrets Manager.
7. **Low running cost.** Open-source software and free tiers wherever they are good enough. See [running-costs.md](running-costs.md).
8. **Ready for AI help.** The system is documented well enough that an AI assistant given these files can answer questions about how the business and the system work. See [../CONVENTIONS.md](../CONVENTIONS.md).

## Out of scope, on purpose

These were considered and left out, so they are not forgotten or rebuilt by accident:

- **Crews of three or more.** Crews are one or two people.
- **Deposits and cards on file.** Payment is due at the time of service. The data model leaves room to add a deposit later.
- **Bitcoin automation before launch.** Bitcoin stays a manual "paid" method until Phase 7.
- **Customer accounts, sign-in codes and personal rebooking links.** Returning customers are matched quietly by phone number instead. See [../reference/returning-customers.md](../reference/returning-customers.md).
- **Replacing GnuCash.** It stays the general ledger.
- **A public control app.** It is reachable only over the owner's Tailscale network.
- **A native phone app.** The control app is a web app that installs to the phone's home screen.

## How success is judged

Each phase ends with a test the owner runs personally. The list is in [roadmap.md](roadmap.md). The project as a whole succeeds when real customers book online, Setmore and WordPress are switched off without losing search traffic, and a month of paid jobs imports into GnuCash and matches the bank deposits.
