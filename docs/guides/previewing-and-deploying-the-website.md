---
title: Previewing and deploying the website
summary: How to preview the website on the workstation against a fake API, run its checks, set up the Cloudflare Pages project, the offline piece and the deploy hook once, and how a change or a pricebook publish reaches the site.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-14
tags: [website, cloudflare, deploy, preview, guide, phase-3]
related: [docs/reference/website-and-seo.md, docs/reference/booking-flow.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/reference/configuration.md, data/configuration.yaml, docs/reference/public-api.md]
---

# Previewing and deploying the website

The website is the Astro project in `site/` ([website-and-seo.md](../reference/website-and-seo.md)). Cloudflare Pages builds it from `main` and serves it, with the offline piece beside it ([decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md)). Nothing about the site runs on the home server.

## Preview it on the workstation

You need Node.js 22 or later (`sudo dnf install nodejs`). From the repository:

```bash
cd site
npm ci
npx playwright install chromium    # once: the browser the tests and checks use
npm run build:test                 # builds against the fake API
npm run preview                    # serves it at http://127.0.0.1:4321
```

`build:test` builds the site against the fake API in `site/tests/fake/api.mjs`, with invented prices and places, and points Turnstile and Google's address suggestions at local fakes. `npm run preview` serves the build with those fakes, so the whole booking flow works, offline form included, with nothing leaving the workstation. In the fake address box, type "100 Example" for an address in the area and "1 Made Up" for one outside it.

To see the real prices, build against the real API: `API_BASE=https://api.dixiedetail.com/api/public/v1 npx astro build`, then `npx astro preview`. The pages show the published pricebook. The booking page switches to its request a time form, because the API only answers browsers on the addresses in `PUBLIC_API_CORS_ORIGINS`.

## Run the checks

The same checks run in GitHub Actions on every pull request that touches `site/` or `data/` (`.github/workflows/site.yml`):

```bash
npm run build:test
npm run check:prices      # no price is computed in the browser
npm run test:unit         # the offline piece: signing, holding, replaying
npm run test:e2e          # the booking flow in a browser, against the fake API
npm run test:lighthouse   # speed and accessibility on a phone
```

The targets are in [website-and-seo.md](../reference/website-and-seo.md#speed-and-accessibility-targets). A failing browser test leaves a trace in `site/test-results/`; open it with `npx playwright show-trace`.

## One-time setup on Cloudflare

Do these in order. They need the Cloudflare account that holds dixiedetail.com, the Bitwarden web vault, and the Turnstile and Google Cloud consoles.

1. **The KV namespace for held requests.** On the workstation, from `site/`: `npx wrangler@4.48.0 login`, then `npx wrangler@4.48.0 kv namespace create OFFLINE_REQUESTS`. Put the id it prints in `site/workers/offline-replay/wrangler.toml` and commit it; it names the namespace and is not a secret.
2. **The Pages project.** In the Cloudflare dashboard, Workers & Pages, Create, Pages, Connect to Git. Pick this repository and name the project `dixie-detail`, which gives the staging address `https://dixie-detail.pages.dev`; if that name is taken, use the address Cloudflare gives instead, everywhere below. Production branch `main`, root directory `site`, build command `npm run build`, output directory `dist`.
3. **Its build settings** (Settings, Variables and Secrets, for Production and Preview), all listed under `website_build_settings` in [data/configuration.yaml](../../data/configuration.yaml):
   - `API_BASE` = `https://api.dixiedetail.com/api/public/v1`;
   - `PUBLIC_TURNSTILE_SITE_KEY` = the Turnstile widget's site key;
   - `PUBLIC_GOOGLE_MAPS_BROWSER_KEY` = the browser key;
   - `NODE_VERSION` = `22`.
4. **The offline piece's bindings** on the same project. Under Settings, Bindings, add a KV namespace binding named `OFFLINE_REQUESTS`, pointing to the namespace from step 1. Under Variables and Secrets, add `API_BASE` as above. Add two secrets, `TURNSTILE_SECRET_KEY` and `OFFLINE_REQUESTS_SIGNING_KEY`, each pasted from the Bitwarden web vault into the dashboard, so neither touches disk. Then redeploy once, so the function picks them up.
5. **The replay Worker.** From `site/`: `npx wrangler@4.48.0 deploy --config workers/offline-replay/wrangler.toml`, then `npx wrangler@4.48.0 secret put OFFLINE_REQUESTS_SIGNING_KEY --config workers/offline-replay/wrangler.toml` and paste the key from Bitwarden at its prompt. It then runs every 5 minutes.
6. **The deploy hook.** On the Pages project, Settings, Builds, Deploy hooks: add one named "Pricebook" for branch `main`. Copy its URL into a new Bitwarden secret `CLOUDFLARE_PAGES_DEPLOY_HOOK` in the "Dixie Detail" project, then restart the stack on the server so the app gets it: `sudo systemctl restart dixie-stack.service`.
7. **Let the staging site call the API.** In `/srv/dixie-detail/.env` on the server, add the staging address to `PUBLIC_API_CORS_ORIGINS`, such as `https://dixiedetail.com,https://www.dixiedetail.com,https://dixie-detail.pages.dev`, then restart the stack.
8. **Turnstile.** In the Turnstile widget's settings, add the staging host name (`dixie-detail.pages.dev`) beside dixiedetail.com.
9. **Google.** In the Google Cloud console, restrict the browser key to the Places API (New), and to the referrers `https://dixiedetail.com/*`, `https://www.dixiedetail.com/*` and `https://dixie-detail.pages.dev/*`.
10. **The photo cards' pictures.** In the control app, open each vehicle class's settings and set its photo card picture to `/images/vehicle-classes/` and the file named for it under `class_images` in [data/site-content.yaml](../../data/site-content.yaml), such as `/images/vehicle-classes/vehicle-class-small.webp`.

Then open the staging address on a phone and make a test booking from a number in `TEST_PHONE_NUMBERS`; `delete_test_records` removes it afterwards ([public-api.md](../reference/public-api.md#test-records)).

## How changes reach the site

- **A merged pull request** that touches the site or the data files starts a build on Cloudflare; it is live in a few minutes. A pull request gets its own preview address on Cloudflare. Its booking page uses the request a time form, because preview addresses are not in `PUBLIC_API_CORS_ORIGINS`.
- **A pricebook version published in the control app** calls the deploy hook once the publish is saved. A version published for a later date is rebuilt for on its effective date by the nightly `rebuild_website --if-due`. `python manage.py rebuild_website` asks for a rebuild by hand, from a one-off app container (`docker compose run --rm --no-deps -T app python manage.py rebuild_website`).
- **A build that can't read the API fails** and the last good build stays live. Cloudflare's build log names the address it couldn't read. Rebuild from the dashboard once the server is back.

## Checking the offline piece

Requests the Worker hasn't delivered yet are in the KV namespace under `pending:`. Any the server refused are kept under `refused:` with the server's answer, so none is lost:

```bash
npx wrangler@4.48.0 kv key list --namespace-id=<the namespace id> --prefix=refused:
npx wrangler@4.48.0 kv key get --namespace-id=<the namespace id> "refused:time-request:<request id>"
```

A refused request needs the owner to contact the customer from what it holds. The Worker's own log (Workers & Pages, `dixie-offline-replay`, Logs) shows each run's counts. A line saying the server refused the signature means the two copies of `OFFLINE_REQUESTS_SIGNING_KEY` on Cloudflare don't match Bitwarden: put them there again, as in steps 4 and 5.

## At the Phase 5 launch

Remove the `X-Robots-Tag` line from `site/public/_headers`, and replace `site/public/robots.txt` with one that allows crawling. Add the redirects for any old address not kept, and point dixiedetail.com at the Pages project. The steps will be in the Phase 5 runbook.
