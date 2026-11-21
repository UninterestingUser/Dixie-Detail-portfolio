---
id: 119
title: "The website moves to Astro 7, because Astro 5 no longer gets security fixes"
summary: "Astro 7.4.13 replaces 5.18.2, bringing fixed sharp and zod. The build finds data/ from the config, since Astro 7 bundles pages first. Output checked page by page against the Astro 5 build."
date: 2026-11-21
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/decisions/0105-the-website-on-cloudflare-pages.md, site/package.json, site/astro.config.mjs, site/src/lib/data.js, docs/guides/previewing-and-deploying-the-website.md]
---

# 0119: The website moves to Astro 7, because Astro 5 no longer gets security fixes

**Status:** accepted · **Date:** 2026-11-21 · **Area:** website

## Context

Decision 0105 built the site on Astro 5.18 rather than Astro 7, which was a week old, and said upgrading later was ordinary work. Astro gives security fixes to the previous major version only, so with Astro 7 current, Astro 5 gets none. On 2026-11-21 Dependabot listed about twenty open alerts against Astro 5 and the `sharp` and `zod` versions it pulls in, one rated critical (code execution through AVIF image optimization), all fixed only in Astro 6 or 7. Most can't reach this site: it is static, with no server adapter, and the build processes only the business's own pictures. Dependabot's two pull requests (#79 and #80) made the jump as a version bump, and both failed the build.

This changes only 0105's choice of version; the rest of 0105 stands.

## Decision

- **Astro 7.4.13,** pinned exactly as before. It brings `sharp` 0.35.5 and `zod` 4.6.7. `npm audit` finds no vulnerability in what the site ships.
- **The build finds `data/` from `astro.config.mjs`.** Astro 7 bundles the pages into `dist/.prerender/` before rendering them, so `src/lib/data.js` could no longer find `data/` relative to its own file (the "ENOENT … site/data/site-content.yaml" that failed #79 and #80). The config, which isn't bundled, sets `DIXIE_DATA_DIR`, which `data.js` already read first. Its own fallback stays for the unit tests, which run it unbundled.
- **Node 22.23.4 or later.** Astro 7's minimum. `site/package.json`'s `engines` says so. `site/.nvmrc` and the Pages setting `NODE_VERSION` stay `22`, which the Site workflow and Pages resolve to a current 22 release.
- **No other change to the site.** `compressHTML: true` keeps the Astro 5 whitespace handling, which Astro 7 still offers (its new default is `"jsx"`).

## How it was checked

The Astro 5 build of `main` and the Astro 7 build were compared page by page: the same files, the same visible text on all 13 pages, and, in Chromium at phone and desktop widths, every element in the same place within 0.22 pixels (from the new CSS minifier's rounding) and the same page heights. The remaining pixel differences are the photos as re-encoded by the newer `sharp`, which look the same. The price check, the 21 unit tests, the 71 browser tests and the Lighthouse targets all pass.

## Alternatives considered

- **Astro 6.** Still behind, and it would be the previous major only until Astro 8, so a second upgrade would follow soon.
- **Stay on Astro 5 and force newer `sharp` and `zod` with npm overrides.** Leaves Astro's own alerts open, and runs Astro 5 with versions it was never tested with.

## Consequences

The site is on a supported Astro again, and the alerts close when this merges. The next Astro major is a planned upgrade, checked the same way: the Site workflow, then a comparison of the built pages.
