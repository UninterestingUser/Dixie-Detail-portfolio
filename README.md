# Dixie Detail

The business system for Dixie Detail LLC, a mobile vehicle detailing business in southeast Tennessee. One PostgreSQL database is the single source of truth for customers, appointments, pricing, billing, staff, bookkeeping and marketing. A private control app runs the business, and a fast public website shows live prices and takes bookings.

**Status:** planning complete, build not started. Next up is Phase 0 (Foundations). See [docs/roadmap.md](docs/roadmap.md).

This repository is private. All rights reserved.

## The system at a glance

| Part | What it is | Where it runs |
| --- | --- | --- |
| Database | PostgreSQL, the single source of truth | Home server ("Server"), in Docker |
| Core app | Django: business logic, REST API, scheduled jobs | Home server, in Docker |
| Control app | Web app served by the core app; installable on the Pixel | Home server, reachable only over Tailscale |
| Public website | Astro static site with the booking flow | Cloudflare (free plan) |
| Site-to-server link | Cloudflare Tunnel, outbound only | Home server |
| Calendar | Two Google Workspace calendars, mirrored from the database | Google |
| Phone and texts | Quo (formerly OpenPhone) | Quo |
| Card payments | Stripe (payment links, Tap to Pay, Cash App Pay) | Stripe |
| Bitcoin | BTCPay Server, Phase 7 | Home server, later |
| Books | GnuCash, fed by an export from the core app | Owner's workstation |

[docs/architecture.md](docs/architecture.md) has the diagram and the reasoning.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Components, data flow, hosting, network, backups |
| [docs/decisions.md](docs/decisions.md) | Every settled decision, with the date and the reason |
| [docs/pricing.md](docs/pricing.md) | How a price is built, size variants, condition, crew time, sales tax |
| [docs/scheduling.md](docs/scheduling.md) | Booking rules, availability, calendars, time-to-leave alerts |
| [docs/integrations.md](docs/integrations.md) | Every outside service, what it is used for, and its status |
| [docs/compliance.md](docs/compliance.md) | Text-message registration, consent and the policy pages |
| [docs/roadmap.md](docs/roadmap.md) | The eight phases, their tasks and their done-when tests |
| [docs/setup/server.md](docs/setup/server.md) | Preparing the home server: Tailscale, battery shutdown, backups |
| [data/price-matrix.csv](data/price-matrix.csv) | The pricebook: 90 prices with one-person job lengths |

## Planned repository layout

Folders appear as each phase starts.

```
backend/      Django project: core app, API, control app, scheduled jobs
website/      Astro public site and booking flow
infra/        Docker Compose, Cloudflare Tunnel, backup scripts
data/         Seed data such as the price matrix
docs/         Everything in the table above
```

## How work is tracked

- **Milestones:** one per phase, named `Phase 0: Foundations` through `Phase 7: Bitcoin`.
- **Issues:** one per task in [docs/roadmap.md](docs/roadmap.md), using the Task template.
- **Branches:** `main` is always deployable. Work happens on short branches named after the issue, such as `12-price-lookup`, merged by pull request.
- **Decisions:** any change to a rule is recorded in [docs/decisions.md](docs/decisions.md) in the same pull request that implements it.

## Secrets

Nothing secret is ever committed. Real values live in a `.env` file on the server, which `.gitignore` excludes. [.env.example](.env.example) lists every variable with no values.
