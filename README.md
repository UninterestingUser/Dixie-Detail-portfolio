# Dixie Detail business system

The booking, scheduling, pricing and back-office system for Dixie Detail LLC, a one-person mobile vehicle detailing business in southeast Tennessee. One PostgreSQL database is the single source of truth for customers, vehicles, appointments, prices, payments, staff and bookkeeping. A private control app runs the business, and a fast public website will show live prices and take bookings.

**Status (October 2026):** Phase 0 (foundations) and Phase 1 (core data and control app) are done. The home server runs the database and the control app, with the pricebook, the pricing engine, the imported job history and screens for customers, jobs, staff and the pricebook. Phase 2 (vehicle catalog) is next. See [docs/overview/roadmap.md](docs/overview/roadmap.md).

**About the public copy.** The working repository is private. A public copy is published from it with [tools/publish-portfolio.sh](tools/publish-portfolio.sh), which rewrites every commit to replace server addresses and a few private details with placeholders. Everything else, including the full commit history, is as built.

## How this was built

This is a real system for a real business, built by its owner working with AI tools. Commits written by Claude Code carry a `Co-Authored-By: Claude` line.

**Kris Grassman, owner**

- **Product and business rules.** Set the goals, the scope and every business rule: pricing, scheduling, payments, sales tax and bookkeeping. Made or approved every decision recorded in [docs/decisions/](docs/decisions/README.md), choosing among options Claude laid out or setting the rule directly.
- **Infrastructure.** Set up and runs the home server (Ubuntu Server, Docker, RAID 5, battery backup) and the services around it: a Tailscale network, a Cloudflare Tunnel, Bitwarden Secrets Manager with a TPM-bound machine token, Google Workspace, and encrypted backups to Google Drive. Ran every command on the server and worked through each failure.
- **Direction and review.** Gives Claude Code each task from a step-by-step runbook, reviews and merges every pull request, and runs the check that closes each step, such as restoring a real backup into a scratch database.
- **Business data.** Supplied the price matrix and the history exported from the earlier tools, and decided every correction to it.
- **Second opinion.** Cross-checks plans, decisions and changes with Grok (xAI) along the way.

**Claude (Anthropic)**

- **Claude, in the Claude app:** planning and research partner. Turned the owner's requirements into the executive plan, the phase runbooks and the task prompts; researched options and rules, such as vehicle data sources, sales tax, payment and messaging providers, and Android location services; designed the documentation structure; and diagnosed server problems from pasted output.
- **Claude Code:** implementer. Wrote the code, tests, scripts, migrations and most of the documentation in this repository, one branch and pull request per task, following [CLAUDE.md](CLAUDE.md).

**Grok (xAI):** an independent second opinion on plans and changes before the owner accepts them.

### How a change happens

1. The owner states a need or a rule.
2. Claude, in the Claude app, turns it into a plan and a task in the phase runbook. The owner reviews it, cross-checking with Grok.
3. Claude Code makes the change on a branch, with tests and updated docs, and opens a pull request.
4. GitHub runs the tests and the documentation check.
5. The owner reviews and merges, deploys to the server, and runs the step's check.
6. A changed rule or design choice gets a decision record in the same pull request.

## What it covers

| Capability | Status |
| --- | --- |
| Home server stack, private and public access, secrets handling, nightly off-site backups with restore tests, monitoring | Running (Phase 0) |
| Data model for customers, vehicles, appointments, pricebook, promotions, billing, staff, bookkeeping and messaging, with change history | Built (Phase 1) |
| Pricebook and pricing engine, import of the earlier records | Built (Phase 1) |
| Control app: installable phone-first shell, sign-in, customer search and customer pages | Built (Phase 1) |
| Control app: schedule and jobs with live prices, maintenance series, staff authorization and assignment, pricebook drafts and publishing | Built (Phase 1) |
| Vehicle catalog from EPA and NHTSA data, with classification rules the owner can edit | Planned (Phase 2) |
| Public website with live estimates and online booking, scheduling settings, Google Calendar sync | Planned (Phase 3) |
| Text messages, time-to-leave alerts, card payments, arrival and departure times | Planned (Phase 4) |
| GnuCash export, tax reports, promotions and staff pay screens | Planned (Phase 6) |

## The system at a glance

| Part | What it is | Where it runs |
| --- | --- | --- |
| Database | PostgreSQL, the single source of truth | Home server, in Docker |
| Core app | Django: business logic, REST API, scheduled jobs | Home server, in Docker |
| Control app | Django pages with htmx, installable on the owner's phone | Home server, reachable only over Tailscale |
| Public website | Astro static site with the booking flow | Cloudflare |
| Site-to-server link | Cloudflare Tunnel, outbound only | Home server |
| Calendar | Two Google Workspace calendars, mirrored from the database | Google |
| Phone and texts | Quo (formerly OpenPhone) | Quo |
| Card payments | Stripe (payment links, Tap to Pay, Cash App Pay) | Stripe |
| Books | GnuCash, fed by an export from the core app | Owner's workstation |

[docs/architecture/system-overview.md](docs/architecture/system-overview.md) has the diagram and the reasoning.

## What the project demonstrates

- A system designed around one source of truth, with every business rule written down and traced to a decision record.
- Production services on self-hosted hardware: Docker Compose under systemd, a reverse proxy with separate private and public entry points, a Cloudflare Tunnel and Tailscale.
- Secrets without plaintext: Bitwarden Secrets Manager, a TPM-sealed credential, and secrets handed to containers as in-memory files.
- Backups that are proven: nightly dumps, encrypted off-site copies with restic, and a restore test into a scratch database.
- Documentation as code for people and AI: structured Markdown and YAML, a docs check on every pull request, and an index for AI tools.
- Directing AI agents on a real project: plans, task prompts, review, and a second-model cross-check.

## Documentation

Start at [docs/README.md](docs/README.md), the map of every document, grouped by purpose: overview, architecture, business rules, decisions, server operations and guides. Structured facts such as services, rules with numbers, settings and secret names live in [data/](data/README.md), with the pricebook in [data/price-matrix.csv](data/price-matrix.csv). [docs/CONVENTIONS.md](docs/CONVENTIONS.md) sets the rules for writing and changing the docs, and [llms.txt](llms.txt) is an index for AI tools.

## Repository layout

```
app/          Django core app: the data model, the health page, and the control app as it is built
caddy/        Caddy configuration: the private and public doors
ops/          systemd units and scripts: start, deploy, back up, restore test, health check
compose.yaml  The Docker stack: PostgreSQL, the app, Caddy, cloudflared
data/         Structured facts and the price matrix
docs/         The documentation; see docs/README.md
tools/        Repository tools: the docs check, the test runner, the portfolio publisher
```

## How work is tracked

- **Phases:** eight, from Phase 0 (foundations) to Phase 7 (Bitcoin), each ending with a check the owner runs. See [docs/overview/roadmap.md](docs/overview/roadmap.md).
- **Branches:** `main` is always deployable. Each task is a short branch merged by pull request, with tests and the docs check passing.
- **Decisions:** any change to a rule or design choice gets a new record in [docs/decisions/](docs/decisions/README.md) in the same pull request.

## Secrets

Every key, password and token lives in Bitwarden Secrets Manager. Nothing secret is committed or stored in plaintext on the server. The server keeps one secret, the Bitwarden machine-account token, encrypted as a systemd credential bound to the server's TPM; services fetch everything else from Bitwarden when they start. `.env` holds only settings that are not secret, and [.env.example](.env.example) lists them along with the names of the Bitwarden secrets.

## Copyright

© 2026 Dixie Detail LLC. All rights reserved. The public copy is shared to show the work; no license to reuse the code or content is granted.
