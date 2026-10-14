---
title: Network and access
summary: How staff reach the private control app over Tailscale, how the public reaches only the health page and booking API through the Cloudflare Tunnel, and which host names the app accepts.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-13
tags: [network, tailscale, cloudflare, security]
related: [docs/architecture/server-and-stack.md, docs/architecture/secrets.md, docs/decisions/0005-tailscale-private-access.md, docs/decisions/0038-two-doors-access-model.md]
---

# Network and access

The core app has two ways in, and Caddy is the only container either way reaches. No port is opened on the pfSense firewall and nothing new listens on the home network.

## The private door: staff over Tailscale

- Caddy listens on `127.0.0.1:8000` on the server and serves the whole app there, including the control app and the Django admin.
- Caddy refuses any request on port 8000 that comes from the `cloudflared` container, which has the fixed address 172.31.250.10 on the tunnel network. A tunnel route pointed at the wrong port by mistake therefore exposes nothing.
- `sudo tailscale serve --bg 8000` publishes that port to the owner's tailnet as `https://server.example-tailnet.ts.net`, with a certificate from Tailscale. `--bg` keeps it running across reboots.
- Only devices signed in to the owner's tailnet can open that address. From the LAN, `http://192.0.2.10:8000` does not connect, which proves nothing listens on the network.
- The server is its own Tailscale node in addition to the pfSense subnet route that advertises the home network. The direct node avoids a clash on outside Wi-Fi networks that also use 192.168.1.x, and it gives the control app a real HTTPS address, which the Pixel needs to install it as an app.
- The server joined without `--accept-routes`, and key expiry is disabled for it in the Tailscale admin console.
- MagicDNS and HTTPS certificates are enabled for the tailnet. Phones need "Use Tailscale DNS" turned on in the Tailscale app to resolve the name.

## The public door: the internet through Cloudflare

- The Cloudflare Tunnel named `dixie-detail` connects outward from the `cloudflared` container to Cloudflare. Its token is the Bitwarden secret `CLOUDFLARE_TUNNEL_TOKEN`.
- The tunnel has one published application route: `api.dixiedetail.com` to `http://caddy:8080`. Cloudflare created the DNS record itself.
- Caddy's port 8080 exists only inside the `dixie_tunnel` Docker network, which holds only Caddy and `cloudflared`, and answers two paths: `/health` and anything under `/api/public/`. Every other path returns "not found", so the admin and control app cannot be reached from the internet even by guessing addresses.
- The app checks the public-door rule a second time. Caddy labels every request with the door it came through, in an `X-Dixie-Entrance` header that overwrites any value the visitor sent, and the app serves only `/health` and `/api/public/` to requests not labelled as coming over the tailnet.
- The public API, once built, does three things: list services and prices, show open slots, and take a booking.
- The WordPress site and the email DNS records were not touched. The rest of `dixiedetail.com` keeps working as before until the launch cutover in Phase 5.

## Host names Django accepts

Django refuses any request whose host name is not in `DJANGO_ALLOWED_HOSTS` in `.env`, with "Bad Request (400)". The setting is a comma-separated list of bare host names, with no `https://` and no spaces. At the end of Phase 0 it holds:

```
DJANGO_ALLOWED_HOSTS=server.example-tailnet.ts.net,api.dixiedetail.com,127.0.0.1,localhost
```

- `server.example-tailnet.ts.net` for the control app over Tailscale
- `api.dixiedetail.com` for the public door
- `127.0.0.1` and `localhost` for checks run on the server itself

The app always accepts `localhost` as well, even if it is missing from the setting, for the container's own health check.

After changing `.env`, run `sudo systemctl restart dixie-stack`. The restart recreates every container, so the app picks up the new value.

## Planned additions

- **Phase 3:** the Astro website on Cloudflare Pages, on a staging address first, calling `api.dixiedetail.com`. Its build is triggered by a deploy hook stored as the Bitwarden secret `CLOUDFLARE_PAGES_DEPLOY_HOOK`.
- **Phase 4:** webhooks from Stripe and Quo arrive through the public door under `/api/public/`, each verified with its own signing secret.
- **Phase 5:** the DNS cutover points `dixiedetail.com` at the new site, with redirects for every old WordPress address.
