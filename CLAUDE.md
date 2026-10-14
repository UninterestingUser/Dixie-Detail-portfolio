# Notes for Claude

This repository holds the Dixie Detail business system. Read this file first, then `docs/README.md`.

## Ground rules

- PostgreSQL is the single source of truth. The website, the calendars and outside services are mirrors or consumers, never sources.
- The business rules in `docs/reference/pricing.md` and `docs/reference/scheduling-and-calendars.md` are settled. Do not change a rule without the owner's say-so, and record any change in `docs/decisions/` in the same pull request.
- Prices come only from `data/price-matrix.csv` and the rules in `docs/reference/pricing.md`. Never hard-code a price.
- The final price is always calculated on the server. The website only displays it.
- The control app is reachable only over Tailscale. Never expose it publicly. The public API does three things: list services and prices, show open slots, take a booking.
- Secrets live only in Bitwarden Secrets Manager (project "Dixie Detail"). Never commit a secret or write one to disk in plaintext: not in `.env`, not in compose files, not in Docker environment variables (Docker saves those in its config on disk), not in logs, not in backups.
- The server's only stored secret is the Bitwarden machine-account token, encrypted with `systemd-creds` at `/etc/credstore.encrypted/dixie-bws-token.cred`. Services load it with `LoadCredentialEncrypted=bws-token:/etc/credstore.encrypted/dixie-bws-token.cred`, fetch their secrets with `bws`, and hand them to containers as files on in-memory mounts, or keep them in process memory.
- `.env` holds non-secret settings only. `.env.example` lists those settings and the names of the Bitwarden secrets.
- Local development uses a separate Bitwarden project with throwaway values, never production secrets.
- Card details never touch the server.
- Texts go only to customers with recorded consent of the right kind (appointment or follow-up). See `docs/reference/text-messages.md`.

## Owner's environment

- Server: Ubuntu Server with Docker, hostname "Server". Clients: Fedora Workstation and a Google Pixel 9a.
- On the server, the code lives at `/srv/dixie-detail`. The systemd unit, ops scripts and docs assume that path.
- Linux-first. Anything the owner runs locally must work on Fedora.
- Eastern time for everything customer-facing.

## Conventions

- One issue per task, one short branch per issue, merged by pull request.
- Plain, specific wording in customer-facing text. Every text message starts with "Dixie Detail:".

## Documentation

- `docs/` and `data/` are the knowledge base for the owner, future staff and the business's AI assistants. Follow `docs/CONVENTIONS.md` for every change.
- Docs are part of done. A pull request that changes behaviour, a setting, a secret name, a server path or a business rule updates the matching docs and data files in the same pull request. A changed rule or design choice also gets a new record in `docs/decisions/`.
- Every docs file has a header block. Use `status: planned` and the future tense for anything not built yet; when you build it, change the status to `current` and the text to the present tense.
- Code is the authority on what exists. If the docs and the code disagree, fix whichever is wrong and say so in the pull request.
- When you solve a problem on the server, add it to `docs/operations/troubleshooting.md`.
- Never put secret values or real customer data in docs, data files, issues or pull requests. Use invented examples.
- Run `python3 tools/check_docs.py` before opening a pull request; it must pass.
