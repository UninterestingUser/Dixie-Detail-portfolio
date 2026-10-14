# Dixie Detail

The business system for Dixie Detail LLC, a mobile vehicle detailing business in southeast Tennessee. One PostgreSQL database is the single source of truth for customers, appointments, pricing, billing, staff, bookkeeping and marketing. A private control app runs the business, and a fast public website shows live prices and takes bookings.

**Status:** Phase 0 (Foundations) is complete apart from the deferred restore test. Phase 1 (Core data and control app) is next. See [docs/overview/roadmap.md](docs/overview/roadmap.md).

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

[docs/architecture/system-overview.md](docs/architecture/system-overview.md) has the diagram and the reasoning.

## Documentation

Start at [docs/README.md](docs/README.md), the map of every document, grouped by purpose: overview, architecture, business rules, decisions, server operations and guides. Structured facts such as services, rules with numbers, settings and secret names live in [data/](data/README.md), with the pricebook in [data/price-matrix.csv](data/price-matrix.csv). [docs/CONVENTIONS.md](docs/CONVENTIONS.md) sets the rules for writing and changing the docs, and [llms.txt](llms.txt) is an index for AI tools.

## Repository layout

Folders appear as each phase starts.

```
app/          Django core app (Phase 0: the /health page; Phase 1 adds the data model and control app)
caddy/        Caddy configuration: the private and public doors
ops/          systemd units and scripts: start, deploy, back up, restore test, health check
compose.yaml  The Docker stack: PostgreSQL, the app, Caddy, cloudflared
website/      Astro public site and booking flow (Phase 3)
data/         Structured facts and the price matrix
docs/         The documentation; see docs/README.md
tools/        Repository tools, such as the documentation check
```

## How work is tracked

- **Milestones:** one per phase, named `Phase 0: Foundations` through `Phase 7: Bitcoin`.
- **Issues:** one per task in [docs/overview/roadmap.md](docs/overview/roadmap.md), using the Task template.
- **Branches:** `main` is always deployable. Work happens on short branches named after the issue, such as `12-price-lookup`, merged by pull request.
- **Decisions:** any change to a rule or design choice gets a new record in [docs/decisions/](docs/decisions/README.md) in the same pull request that implements it.

## Secrets

Every key, password and token lives in Bitwarden Secrets Manager, in the Dixie Detail project. Nothing secret is committed or stored in plaintext on the server. The server keeps one secret, the Bitwarden machine-account token, encrypted as a systemd credential; services fetch everything else from Bitwarden when they start. `.env` holds only settings that are not secret, and [.env.example](.env.example) lists them along with the names of the Bitwarden secrets.
