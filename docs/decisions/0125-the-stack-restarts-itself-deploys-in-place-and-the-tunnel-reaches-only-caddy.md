---
id: 125
title: "The stack restarts itself, deploys never take it down first, the health check has its own credential, and the tunnel can reach only Caddy"
summary: "dixie-stack.service retries every minute without limit; deploy.sh fetches and builds before touching the stack, then recreates only what changed; the ping URL is a systemd credential; a host firewall confines the tunnel."
date: 2026-11-22
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [ops/dixie-stack.service, ops/stack-start.sh, ops/deploy.sh, ops/lib/deploy.sh, ops/lib/stack.sh, ops/health-credential.sh, ops/public-health.sh, ops/tunnel-firewall.sh, ops/dixie-tunnel-firewall.service, ops/check-tunnel-isolation.sh, tools/test-deploy.sh, tools/test-tunnel-firewall.sh, docs/decisions/0070-nightly-backup-at-2-45.md, docs/architecture/server-and-stack.md, docs/architecture/network-and-access.md]
---

# 0125: The stack restarts itself, deploys never take it down first, the health check has its own credential, and the tunnel can reach only Caddy

**Status:** accepted · **Date:** 2026-11-22 · **Area:** infrastructure

## Context

A review found four weaknesses (findings H2 and M2):

- **No retry.** `dixie-stack.service` didn't retry. After a power cut, or with the internet still down at boot, Bitwarden was unreachable, the start failed, and the site stayed down until someone restarted it by hand.
- **Deploys took the site down.** `deploy.sh` restarted the whole stack (`docker compose down`, then up). The site was down for every deploy, and a deploy whose Bitwarden fetch or image build failed left it down.
- **Bitwarden calls every 10 minutes.** The public health check fetched its ping URL from Bitwarden on every run. Those calls were behind the 429 answers decision 0070 worked around.
- **cloudflared could reach the host's networks.** It holds the only connection from the internet into the server, and nothing but Caddy's own rule kept it, or anything else on the tunnel network, from the LAN, the tailnet, the other Docker networks or the host.

## Decision

- **The stack retries until it runs.** `dixie-stack.service` has `Restart=on-failure`, `RestartSec=60` and `StartLimitIntervalSec=0`. `stack-start.sh` exits non-zero on any failure: Bitwarden unreachable or refusing (after the 429 retries), a secret missing, or a container that doesn't come up running and healthy (`docker compose up --wait`).
- **Deploys never take the stack down first.** After the pull, `deploy.sh` works in this order:
  1. It fetches the secrets into a fresh in-memory folder and builds the images. If either fails, it stops, says the running stack was left as it was, and has changed nothing.
  2. It installs the units, timers, folders and the health check's credential.
  3. It swaps the new secret files in, and recreates only the containers whose image or settings changed (`docker compose up --wait`, never `down`, never `--force-recreate`). When the stack isn't running, it starts it instead.

  A change to `.env` or a secret still needs `systemctl restart dixie-stack`, which the docs say.
- **The health check's ping URL is its own credential.** It is the Bitwarden secret `HEALTHCHECKS_PUBLIC_URL`, encrypted with `systemd-creds --with-key=host+tpm2` to `/etc/credstore.encrypted/dixie-healthchecks-public-url.cred`. `ops/health-credential.sh` creates or refreshes it, and `deploy.sh` creates it when missing. `dixie-public-health.service` loads it with `LoadCredentialEncrypted=`, and the check never calls Bitwarden.
- **The tunnel can reach only Caddy.** `ops/tunnel-firewall.sh` is applied by `dixie-tunnel-firewall.service` after Docker starts, and again when Docker restarts. Traffic from the tunnel network (172.31.250.0/24) is handled in two chains:
  - **`DIXIE-TUNNEL`, from `DOCKER-USER`:** allows replies, and Caddy's public door (Caddy now at the fixed address 172.31.250.20, TCP 8080). It drops every private range: 10/8, 172.16/12, 192.168/16, 100.64/10 and 169.254/16. Public internet addresses go on to Docker's own rules.
  - **`DIXIE-TUNNEL-HOST`, from `INPUT`:** drops everything to the host's own addresses except replies.

  Both chains are replaced in one atomic `iptables-restore`, so applying again never leaves a gap. `cloudflared` uses the public resolvers 1.1.1.1 and 1.0.0.1, since a LAN resolver is dropped. Caddy's private door refuses the whole tunnel network except its gateway, which is the host's own port forwarding. `dixie-stack.service` starts after the firewall. It *wants* the firewall rather than requiring it, so a firewall failure doesn't take the site down; `ops/check-tunnel-isolation.sh` shows the gap.
- **Checks.**
  - `tools/test-deploy.sh`, with fakes, covers deploys that fail at the fetch or the build and leave the stack running, a deploy that recreates only what changed, and a stopped stack being started. It also covers the start failing on a non-429 Bitwarden error and on an unhealthy container, and the unit's restart lines.
  - `tools/test-tunnel-firewall.sh` applies the rules with the real `iptables` in a network namespace of its own.
  - `ops/check-tunnel-isolation.sh` checks the server with real traffic from a throwaway container on the tunnel network:
    - **Must be reachable:** the public door, a public address and public DNS.
    - **Must be refused:** the control-app door, the host through the gateway and its LAN address, and the router. It first confirms each refused target is actually open from the host, so a closed port doesn't count as a pass.

## Alternatives considered

- **`Restart=always`.** Would also restart a deliberately stopped stack.
- **Blue-green deploys with two stacks.** More than a one-server business needs; recreating only the changed containers keeps the gap to the few seconds a container takes to start.
- **cloudflared on the host instead of in Docker.** Then nothing would separate it from the host at all.
- **Docker's `internal: true` for the tunnel network.** It blocks the internet too, which cloudflared needs to reach Cloudflare.

## Consequences

After a power or internet cut the site comes back by itself once Bitwarden answers. A deploy changes the running site only in its last step, and only the containers that changed restart. A failed deploy is harmless. Bitwarden is called only by deploys, starts and the scheduled jobs. A compromised `cloudflared` could reach only Caddy's public door and the internet.

Applying the firewall needs Docker's iptables firewall (`DOCKER-USER`). If Docker moves to its nftables backend, the firewall unit fails loudly and the check shows it.
