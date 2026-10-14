---
id: 2
title: "Astro static website on Cloudflare's free plan"
summary: "The public website is a static Astro site on Cloudflare, for speed, search ranking, and staying up when the home server is down."
date: 2026-10-07
area: stack
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/website-and-seo.md]
---

# 0002: Astro static website on Cloudflare's free plan

**Status:** accepted · **Date:** 2026-10-07 · **Area:** stack

## Context

The WordPress site is slow, builds pages on request, and would go down with the home server if self-hosted.

## Decision

Build the public site with Astro as static pages with almost no JavaScript, hosted on Cloudflare's free plan. Prices are published at build time; the booking flow reads live data through the tunnel.

## Alternatives considered

- **Keep WordPress.** Slower, and its booking options are what the business is moving away from.
- **Serve the site from the home server.** The site would go down with the server.

## Consequences

Unlimited static requests and bandwidth at no cost. A pricebook change triggers a rebuild. When the server is down the site still loads and the booking form becomes a request form.
