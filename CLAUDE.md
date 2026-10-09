# Notes for Claude

This repository holds the Dixie Detail business system. Read this file first, then `docs/decisions.md`.

## Ground rules

- PostgreSQL is the single source of truth. The website, the calendars and outside services are mirrors or consumers, never sources.
- The business rules in `docs/pricing.md` and `docs/scheduling.md` are settled. Do not change a rule without the owner's say-so, and record any change in `docs/decisions.md` in the same pull request.
- Prices come only from `data/price-matrix.csv` and the rules in `docs/pricing.md`. Never hard-code a price.
- The final price is always calculated on the server. The website only displays it.
- The control app is reachable only over Tailscale. Never expose it publicly. The public API does three things: list services and prices, show open slots, take a booking.
- Never commit secrets. Real values live in `.env` on the server; `.env.example` lists the names.
- Card details never touch the server.
- Texts go only to customers with recorded consent of the right kind (appointment or follow-up). See `docs/compliance.md`.

## Owner's environment

- Server: Ubuntu Server with Docker, hostname "Server". Clients: Fedora Workstation and a Google Pixel 9a.
- Linux-first. Anything the owner runs locally must work on Fedora.
- Eastern time for everything customer-facing.

## Conventions

- One issue per task, one short branch per issue, merged by pull request.
- Keep the docs current: when code changes behavior described in `docs/`, update the doc in the same pull request.
- Plain, specific wording in customer-facing text. Every text message starts with "Dixie Detail:".
