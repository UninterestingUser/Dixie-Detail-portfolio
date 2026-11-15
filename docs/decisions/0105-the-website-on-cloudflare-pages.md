---
id: 105
title: "The website on Cloudflare Pages: built from the API, a baked-in price table, and an offline piece in Pages Functions, KV and a scheduled Worker"
summary: "The site in site/ reads every price from the API at build time and fails rather than publish without one; the browser never works a price out; offline forms are held in Workers KV and replayed, signed."
date: 2026-11-14
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-14
supersedes: []
superseded_by: []
related: [docs/reference/website-and-seo.md, docs/reference/booking-flow.md, docs/reference/public-api.md, docs/guides/previewing-and-deploying-the-website.md, docs/decisions/0002-astro-on-cloudflare.md, docs/decisions/0031-website-design-direction.md, docs/decisions/0032-address-validation-with-places.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0100-public-api-quotes-and-bookings.md, docs/decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md]
---

# 0105: The website on Cloudflare Pages: built from the API, a baked-in price table, and an offline piece in Pages Functions, KV and a scheduled Worker

**Status:** accepted · **Date:** 2026-11-14 · **Area:** website

## Context

Phase 3, Step 6 builds the website on a staging address (decision 0002), to the approved mockups (decision 0031). The site must show only the server's prices (decision 0059), keep working when the home server is down, and take a "request a time" form that Cloudflare holds and replays signed (decision 0100). It must also keep working when Google's address suggestions fail, such as once the day's limit is used up, and everything must fit Cloudflare's free plan.

## Decision

- **The site lives in `site/`.** It is a static Astro site, on Astro 5.18, the last release of a line with a long track record, rather than the newest major. Only the booking page, and the homepage's year, make and model picker, run scripts.
- **Every address of the current site is kept,** with its title and description: the homepage, `/services/`, `/reviews/`, `/about/`, `/contact/`, the three city pages and the two policy pages. The new pages are added beside them: `/services/<category>/`, `/faq/` and `/book/`.
- **Prices come from the public API at build time.** That covers the service and "from" prices, the classes, the condition levels, the consent wording and the structured data for search engines. If the API can't be read the build fails, and Cloudflare keeps serving the last good build. Text comes from the data files: `data/site-content.yaml` (the owner's words) and `data/site-pages.yaml` (carried over from the current site).
- **The browser never works a price out.** The estimate card shows the latest quote's numbers as they arrive. For the offline form, the server publishes `GET price-table`, the pricing engine's total and time on site for every job bookable online. The build bakes it into the booking page, and the browser only looks a total up. A check in CI refuses any number conversion or arithmetic beside a money name in the browser code, and the browser tests run against a fake server whose totals are not the sums of their lines.
- **When the server can't be reached, or Google's suggestions fail,** the booking form becomes the "request a time" form and a quote request goes without photos. Both post to a **Cloudflare Pages Function** at `/offline/…`, which:
  - checks the Turnstile token;
  - tries the server at once, signed, so a Google outage alone costs no wait;
  - otherwise holds the request in **Workers KV** for up to 14 days.
- **A scheduled Worker replays held requests.** Every 5 minutes it sends each held request, signed, and drops it once the server takes it. It stops at the first sign the server is still down. A request the server refuses (4xx) is kept aside in KV with the server's answer, never lost. This fits the free plan: at most 288 KV list calls a day, and one write for each request that had to be held.
- **Address suggestions use the Places Autocomplete (New) web service from the browser,** with the browser key and a session token the server reuses for its own lookup. The JavaScript library's session token can't be handed to the server, and the suggestions before a pick should not be billed (decision 0032).
- **Turnstile runs when a form is sent,** invisible unless Cloudflare asks the visitor to tick it. A quote request with photos runs it once more, when the first photo is picked, to open the upload session.
- **Photos shrink in the browser when it can read them,** to at most 2560 pixels as a JPEG; any other photo goes as it is, within the API's size limit.
- **Staging is not indexed:** `site/public/_headers` sends `X-Robots-Tag: noindex, nofollow` and `site/public/robots.txt` disallows everything. The Phase 5 launch removes both.
- **Rebuilds:** publishing a pricebook version calls the Cloudflare Pages deploy hook once the publish commits. A nightly `rebuild_website --if-due` rebuilds when a version published earlier takes effect that day.
- **No review is written for the site.** Reviews come only from the owner, in an optional `data/reviews.yaml`. None is committed: the current site's reviews carry customers' names, and the repository is published as a portfolio, so the owner decides how to supply them. Until then the reviews section links to the Google reviews, and shows no rating figure.
- **The mockup's map placeholder is a list of the five counties,** with the current site's text for each.

## Alternatives considered

- **Compute offline totals in the browser from the price list.** Simpler, but a second pricing engine in the browser is exactly what decision 0059 rules out, and it would drift.
- **Cloudflare Queues or Durable Objects for the offline piece.** Queues need a consumer Worker anyway and have tighter free-plan limits for this use; Durable Objects add a class and storage to run. KV and a schedule are enough for a handful of requests during an outage.
- **Astro 7.** The newest major was a week old when the site was built; 5.18 is the release the patterns and tests here were written against. Upgrading later is ordinary work.
- **Show the current site's reviews.** They are real, but they name customers, and CLAUDE.md keeps customer data out of the repository.

## Consequences

- Two Cloudflare pieces now hold copies of Bitwarden secrets: the Pages project (`TURNSTILE_SECRET_KEY`, `OFFLINE_REQUESTS_SIGNING_KEY`) and the Worker (`OFFLINE_REQUESTS_SIGNING_KEY`). Bitwarden stays the source, and each copy is put there from Bitwarden without touching disk; a change means putting it there again.
- The site is only as current as its last build: a price change reaches it with the deploy hook, within minutes.
- CI builds the site against a fake API and checks it in a browser on every pull request that touches `site/` or `data/`, including Lighthouse's speed and accessibility targets on a phone.
