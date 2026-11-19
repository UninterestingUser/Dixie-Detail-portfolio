---
id: 109
title: "Website reviews are kept in the control app and read by the site's build through the public API"
summary: "Managers keep website reviews on a control app screen, never in a data file, so customers' names stay out of the repository; the public API serves the shown ones and the site reads them at build time."
date: 2026-11-19
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-19
supersedes: []
superseded_by: []
related: [docs/reference/website-and-seo.md, docs/reference/public-api.md, docs/reference/control-app.md, docs/guides/managing-website-reviews.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/decisions/0063-public-portfolio-copy.md, docs/decisions/0038-two-doors-access-model.md]
---

# 0109: Website reviews are kept in the control app and read by the site's build through the public API

**Status:** accepted · **Date:** 2026-11-19 · **Area:** website

## Context

The website's reviews section waited on the owner to decide how to supply reviews. A data file, `data/reviews.yaml`, was planned, but reviews carry customers' names, and this repository is published as a public portfolio copy ([decision 0063](0063-public-portfolio-copy.md)). On 2026-11-19 the owner chose to keep them in the control app. This changes that one point of [decision 0105](0105-the-website-on-cloudflare-pages.md), which left the choice open.

## Decision

- **A Reviews screen in the control app,** under Account, for managers only. Each review has the reviewer's name as shown (first name and last initial, as on Google), the text, its date, an optional star rating (1 to 5) and an optional link to the Google review. Reviews can be added, edited, moved up or down, shown or hidden, and deleted. Their change history is kept, as for other edited records ([decision 0050](0050-change-history-simple-history.md)).
- **Reviews are kept only in the database:** never in a data file, a fixture with real names or the portfolio copy. Tests use invented names.
- **The public API serves the shown reviews** at `GET reviews`, in the screen's order, for the site's build. This is a read alongside the pricebook, outside the three things the public API was first described as doing (list services and prices, show open slots, take a booking); it gives out only what the website already shows.
- **The site reads them at build time, like prices.** Saving any change on the Reviews screen asks Cloudflare Pages to rebuild through the deploy hook, as a pricebook publish does, once the change is saved. A failed call is logged and never stops the save.
- **The site shows** the name, the text and the stars when given, a link to the review on Google when given, and the link to all the Google reviews. No combined rating figure. With none shown, the section keeps only the link to Google, as before.

## Alternatives considered

- **`data/reviews.yaml`.** Puts customers' names in the repository and its public copy.
- **A Google Places reviews feed.** Google returns at most five reviews of its own choosing, its terms limit how they are shown and stored, and each build would spend a billed call.
- **Showing reviews by calling the API from the browser.** Adds a request to every page view and a dependency on the server being up, for text that changes rarely.

## Consequences

A review goes live within a few minutes of being saved, without a pull request. A site build now also reads `GET reviews`; like the pricebook, if it can't, the build fails and the last good build stays live. The one exception is a 404, which a server deployed before the endpoint existed gives: the build goes on with no reviews and a warning, so the site's change and the server's can be deployed in either order. `data/reviews.yaml` is no longer read.
