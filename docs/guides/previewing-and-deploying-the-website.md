---
title: Previewing and deploying the website
summary: How to preview the website on the workstation against a fake API, run its checks, set up the Cloudflare Pages project, the offline piece and the deploy hook once, and how a change or a pricebook publish reaches the site.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-22
tags: [website, cloudflare, deploy, preview, guide, phase-3]
related: [docs/decisions/0116-worker-deploys-look-up-the-namespace.md, site/workers/offline-replay/deploy.sh, docs/decisions/0114-offline-requests-kept-whatever-they-hold.md, docs/decisions/0115-address-lookup-sessions-and-a-public-share.md, docs/reference/website-and-seo.md, docs/reference/booking-flow.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/reference/configuration.md, data/configuration.yaml, docs/reference/public-api.md]
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

To see the real prices, build against the real API with the server running: `API_BASE=https://api.dixiedetail.com/api/public/v1 PUBLIC_TURNSTILE_SITE_KEY=<the site key> PUBLIC_GOOGLE_MAPS_BROWSER_KEY=<the browser key> npx astro build`, then `npx astro preview`. A build with any of those three empty stops at once with a message naming it. The pages show the published pricebook. The booking page switches to its request a time form, because the API only answers browsers on the addresses in `PUBLIC_API_CORS_ORIGINS`.

## Run the checks

The same checks run in GitHub Actions on every pull request that touches `site/` or `data/` (`.github/workflows/site.yml`):

```bash
npm run build:test
npm run check:prices      # no price is computed in the browser
npm run test:unit         # the offline piece, the required settings, the fake API against the real API's shapes, and the font's characters (after a build)
npm run test:e2e          # the booking flow in a browser, against the fake API
npm run test:lighthouse   # speed and accessibility on a phone
```

The fake API must answer with the real API's shapes, recorded in [data/public-api-shapes.yaml](../../data/public-api-shapes.yaml); `npm run test:unit` checks it, and `tools/run-tests.sh` checks the real API against the same file ([public-api.md](../reference/public-api.md#the-answers-shapes-are-a-tested-contract)). The targets are in [website-and-seo.md](../reference/website-and-seo.md#speed-and-accessibility-targets). A failing browser test leaves a trace in `site/test-results/`; open it with `npx playwright show-trace`.

## One-time setup on Cloudflare

Do these in order. They need the Cloudflare account that holds dixiedetail.com, the Bitwarden web vault, and the Turnstile and Google Cloud consoles.

1. **The KV namespace for held requests.** On the workstation, from `site/`: `npx wrangler@4.48.0 login`, then `npx wrangler@4.48.0 kv namespace create OFFLINE_REQUESTS`. Leave `site/workers/offline-replay/wrangler.toml` as it is: its namespace id is a placeholder, and the Worker's deploy script looks the real id up by the namespace's title, `OFFLINE_REQUESTS` ([decision 0116](../decisions/0116-worker-deploys-look-up-the-namespace.md)). Keep that title, and don't make a second namespace with it.
2. **The Pages project.** In the Cloudflare dashboard, Workers & Pages, Create, Pages, Connect to Git. Pick this repository and name the project `dixie-detail`, which gives the staging address `https://dixie-detail.pages.dev`; if that name is taken, use the address Cloudflare gives instead, everywhere below. Production branch `main`, root directory `site`, build command `npm run build`, output directory `dist`.
3. **Its build settings** (Settings, Variables and Secrets, for Production and Preview), all listed under `website_build_settings` in [data/configuration.yaml](../../data/configuration.yaml). Add each as type **Text**, not Secret: they are public, and the build can't read a Secret. A build with `API_BASE`, `PUBLIC_TURNSTILE_SITE_KEY` or `PUBLIC_GOOGLE_MAPS_BROWSER_KEY` empty stops with a message naming it:
   - `API_BASE` = `https://api.dixiedetail.com/api/public/v1`;
   - `PUBLIC_TURNSTILE_SITE_KEY` = the Turnstile widget's site key;
   - `PUBLIC_GOOGLE_MAPS_BROWSER_KEY` = the browser key;
   - `NODE_VERSION` = `24`, Node 24 LTS, the same as `site/.nvmrc` ([decision 0121](../decisions/0121-ubuntu-26-04-gnu-timeout-and-node-24.md)). The build log's first lines name the version Cloudflare used.
4. **The offline piece's bindings** on the same project. Under Settings, Bindings, add a KV namespace binding named `OFFLINE_REQUESTS`, pointing to the namespace from step 1. Under Variables and Secrets, add `API_BASE` as above. Add two secrets, `TURNSTILE_SECRET_KEY` and `OFFLINE_REQUESTS_SIGNING_KEY`, as type **Secret**, the only two on this project, each pasted from the Bitwarden web vault into the dashboard, so neither touches disk. Then redeploy once, so the function picks them up.
5. **The replay Worker.** From the repository: `site/workers/offline-replay/deploy.sh` (see [Deploying the replay Worker](#deploying-the-replay-worker)). Then, from `site/`, `npx wrangler@4.48.0 secret put OFFLINE_REQUESTS_SIGNING_KEY --config workers/offline-replay/wrangler.toml` and paste the key from Bitwarden at its prompt. Then `npx wrangler@4.48.0 secret put HEALTHCHECKS_OFFLINE_URL --config workers/offline-replay/wrangler.toml` and paste the offline requests check's ping address from Bitwarden the same way ([monitoring.md](../operations/monitoring.md#the-offline-requests-check), [decision 0114](../decisions/0114-offline-requests-kept-whatever-they-hold.md)). It then runs every 5 minutes and reports each run to that check.
6. **The deploy hook.** On the Pages project, Settings, Builds, Deploy hooks: add one named "Pricebook" for branch `main`. Copy its URL into a new Bitwarden secret `CLOUDFLARE_PAGES_DEPLOY_HOOK` in the "Dixie Detail" project, then restart the stack on the server so the app gets it: `sudo systemctl restart dixie-stack.service`.
7. **Let the staging site call the API.** In `/srv/dixie-detail/.env` on the server, add the staging address to `PUBLIC_API_CORS_ORIGINS`, such as `https://dixiedetail.com,https://www.dixiedetail.com,https://dixie-detail.pages.dev`, then restart the stack. Each entry is `https://` and the host name only, with no trailing slash and no path. The app trims a stray slash or space, and refuses to start, naming the entry, if one is still not a bare origin. The app's log shows the list in use: `docker compose logs app | grep "CORS origins"`. Then check from the workstation:

   ```bash
   curl -s -o /dev/null -D - -H "Origin: https://dixie-detail.pages.dev" https://api.dixiedetail.com/api/public/v1/vehicles/years
   ```

   The headers should include `access-control-allow-origin: https://dixie-detail.pages.dev`. Without it, every call from the staging site is refused with a 403, "This address can't be used from that website".
8. **Turnstile.** In the Turnstile widget's settings, add the staging host name (`dixie-detail.pages.dev`) beside dixiedetail.com.
9. **Google.** In the Google Cloud console, restrict the browser key to the Places API (New), and to the referrers `https://dixiedetail.com/*`, `https://www.dixiedetail.com/*` and `https://dixie-detail.pages.dev/*`.
10. **The photo cards' pictures.** In the control app, open each vehicle class's settings and set its photo card picture to `/images/vehicle-classes/` and the file named for it under `class_images` in [data/site-content.yaml](../../data/site-content.yaml), such as `/images/vehicle-classes/vehicle-class-small.webp`.

Then open the staging address on a phone and make a test booking from a number in `TEST_PHONE_NUMBERS`; `delete_test_records` removes it afterwards ([public-api.md](../reference/public-api.md#test-records)).

### Testing the offline form on staging

Order matters, because the build reads the API:

1. **With the server running,** start a build (or let a merge start one) and wait for it to finish. A build started while the server is down fails, and the last good build stays live.
2. **Then stop the server,** such as `sudo systemctl stop dixie-stack.service`, or stop the tunnel.
3. **Open the booking page.** It should say it can't reach the booking system and show the request a time form. Send a request from a number in `TEST_PHONE_NUMBERS`; it should say "Request sent", and the request waits in KV under `pending:` ([Checking the offline piece](#checking-the-offline-piece)).
4. **Start the server again.** Within 5 minutes the Worker replays the request, and it appears in the control app as a website request.

If a send fails instead, the form says so with the phone number and keeps what was typed. The browser's console names the cause, such as a Turnstile error.

## How changes reach the site

- **A merged pull request** that touches the site or the data files starts a build on Cloudflare; it is live in a few minutes. A pull request gets its own preview address on Cloudflare. Its booking page uses the request a time form, because preview addresses are not in `PUBLIC_API_CORS_ORIGINS`.
- **A pricebook version published in the control app** calls the deploy hook once the publish is saved. A version published for a later date is rebuilt for on its effective date by the nightly `rebuild_website --if-due`. `python manage.py rebuild_website` asks for a rebuild by hand, from a one-off app container (`docker compose run --rm --no-deps -T app python manage.py rebuild_website`).
- **A build that can't read the API fails** and the last good build stays live, so the server must be running for any build, a deploy hook's included. Cloudflare's build log names the address it couldn't read. Rebuild from the dashboard once the server is back.
- **A build with a required setting empty fails** at once, and its log names the setting.

## Checking the offline piece

Requests the Worker hasn't delivered yet are in the KV namespace under `pending:`. The server keeps every signed request it can read, listing any problem for the owner ([decision 0114](../decisions/0114-offline-requests-kept-whatever-they-hold.md)), so a refusal is rare: a body that isn't JSON or has no request id. Any the server refused are kept under `refused:` with the server's answer, so none is lost, and the offline requests check in Healthchecks fails until they are dealt with:

```bash
id=$(workers/offline-replay/deploy.sh --id)     # from site/; looks the namespace up by its title
npx wrangler@4.48.0 kv key list --namespace-id="$id" --prefix=refused:
npx wrangler@4.48.0 kv key get --namespace-id="$id" "refused:time-request:<request id>"
```

A refused request needs the owner to contact the customer from what it holds; then delete the key with `npx wrangler@4.48.0 kv key delete --namespace-id="$id" "refused:time-request:<request id>"`, and the check turns green on the next run. The Worker's own log (Workers & Pages, `dixie-offline-replay`, Logs) shows each run's counts, never a request. A line saying the server refused the signature means the two copies of `OFFLINE_REQUESTS_SIGNING_KEY` on Cloudflare don't match Bitwarden: put them there again, as in steps 4 and 5.

## Deploying the replay Worker

Deploy the Worker with its script, from anywhere in the repository on the workstation, after `npx wrangler@4.48.0 login`:

```bash
site/workers/offline-replay/deploy.sh --dry-run   # shows the bindings, uploads nothing
site/workers/offline-replay/deploy.sh             # deploys
```

`wrangler.toml` keeps a placeholder for the KV namespace id. The script asks the Cloudflare account for the namespace titled `OFFLINE_REQUESTS`, writes a copy of `wrangler.toml` with the real id beside it (git ignores it), deploys with the copy and removes it. So the id is never committed or left as a local change, and nothing has to be edited before or after a deploy ([decision 0116](../decisions/0116-worker-deploys-look-up-the-namespace.md)). It stops with a message, and deploys nothing, when wrangler isn't signed in, when no namespace or more than one has that title, or when `wrangler.toml` holds a real id instead of the placeholder. `deploy.sh --id` prints the id only, for the `kv key` commands in [Checking the offline piece](#checking-the-offline-piece). Its tests run with `tools/run-tests.sh` (`tools/test-worker-deploy.sh`, with a fake wrangler).

Deploy again after any change to the Worker, its shared code in `site/shared/offline.js`, or `wrangler.toml`. The Worker's secrets stay in place across deploys.

## At the Phase 5 launch

Remove the `X-Robots-Tag` line from `site/public/_headers`, and replace `site/public/robots.txt` with one that allows crawling. Add the redirects for any old address not kept, and point dixiedetail.com at the Pages project. The steps will be in the Phase 5 runbook.
