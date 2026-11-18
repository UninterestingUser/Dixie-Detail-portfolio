---
title: Website and SEO
summary: The Astro website on Cloudflare Pages - its pages and addresses, where its text, photos and prices come from, how it stays current, the speed and accessibility targets, and the search-ranking safeguards for the launch.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-18
tags: [website, seo, design, astro, cloudflare, phase-3]
related: [docs/reference/booking-flow.md, docs/guides/previewing-and-deploying-the-website.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/decisions/0002-astro-on-cloudflare.md, docs/decisions/0031-website-design-direction.md, docs/decisions/0104-portfolio-copy-leaves-out-unlicensed-pictures.md, data/site-content.yaml, data/site-pages.yaml, docs/reference/public-api.md]
---

# Website and SEO

The new website is a static Astro site in `site/`, on Cloudflare's free plan ([decision 0002](../decisions/0002-astro-on-cloudflare.md), [decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md)). It is built (Phase 3, Step 6) and runs on a staging address, kept out of search, until the Phase 5 launch replaces the WordPress site. The look follows the mockups approved on the design canvas "Dixie Detail Website Mockups" (https://claude.ai/artifact/SEu6MoMF3yauwcTDhuxwkL). How to preview and deploy it is in [../guides/previewing-and-deploying-the-website.md](../guides/previewing-and-deploying-the-website.md).

## Pages and addresses

Every address of the current site is kept, with its title and search description, so no link breaks and moved content keeps ranking.

| Address | Page | On the current site |
| --- | --- | --- |
| `/` | Homepage | Yes |
| `/services/` | The five service categories with their photos and "from" prices | Yes |
| `/services/detailing/`, `/services/paint-correction/`, `/services/headlight-restoration/`, `/services/shampoo-and-extraction/`, `/services/motorcycle-detail/` | One page per category: each service's full description and its prices for each vehicle class and size | New |
| `/cleveland-tn-mobile-detailing/`, `/athens-tn-mobile-detailing/`, `/chattanooga-tn-mobile-detailing/` | The city pages, with their own questions | Yes |
| `/reviews/`, `/about/`, `/contact/` | Reviews, the owner's story, how to reach us | Yes |
| `/faq/` | Every common question | New |
| `/book/` | The booking flow ([booking-flow.md](booking-flow.md)) | New |
| `/privacy-policy/`, `/sms-terms/` | The two policy pages, linked in the footer | Yes |

Every address ends in a slash, as WordPress's do. The Phase 5 launch adds redirects for any other old address, such as WordPress's own feeds.

## Homepage structure

The homepage drops from nine sections to fewer, and the content that leaves moves to its own pages instead of being deleted, so each page can rank for its own search, such as "paint correction Cleveland TN". From the owner's direction (2026-10-10):

- The full-width hero photo with a 40% black shade, the script logo, and a "Get your exact price" year, make and model picker that opens the booking flow with the vehicle filled in.
- A plain red band under the hero, with no text, the same thickness on phones.
- The "Make your vehicle shine" section with its two side-by-side photos, and the three steps of how it works.
- Services with "from" prices read from the pricebook, one card per category.
- The service area, with the three city pages and a short note on each of the five counties. The mockup's map placeholder is that county list for now.
- The reviews section, over the locked, non-scrolling background photo with a 50% shade, after "We come to you".
- The first three common questions with a red call-to-action card, and the charcoal footer with a red top edge.

## Colors and type

- Red #CC0000 is the base: buttons, the band under the hero, review cards and the call-to-action card.
- Navy #002D65 is the accent: small labels, prices, links, finished booking steps, and the booking estimate card and its phone bar.
- Headings are near-black, in Archivo, condensed and uppercase; body text is Archivo too, trimmed and served with the site. The footer is charcoal (#141518) with a red top edge.
- Footer social links are round logo icons (Facebook, X, Instagram, Google), not text. The Google icon links to the Google Business Profile review link in [data/business.yaml](../../data/business.yaml).

## Where the content comes from

| What | Where | How the site uses it |
| --- | --- | --- |
| Service and add-on names, prices, "from" prices, vehicle classes, sizes, condition levels, payment methods, consent wording, photo cards | The public API ([public-api.md](public-api.md)) | Read when the site is built. If the API can't be read, the build fails and the last good build stays live. |
| The price table: the server's total for every job bookable online | `GET price-table` | Baked into the booking page for the offline form; the browser only looks totals up ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)) |
| Page and card text in the owner's words, the condition level cards, and which picture goes with each class and page | [data/site-content.yaml](../../data/site-content.yaml) | Read at build time. Service names match the price book; prices never come from this file. |
| Page titles and descriptions, how it works, the counties, the questions, the about page and the city pages | [data/site-pages.yaml](../../data/site-pages.yaml) | Carried over word for word from the current site. Prices the old pages wrote out are now filled from the pricebook, such as `{from:Full Detail}`. |
| Real reviews | An optional `data/reviews.yaml`, a list of `name`, `text` and `source` | None yet: the owner decides how to supply them, because they name customers and this repository is published as a portfolio. Until then the reviews section links to the Google reviews and shows no rating figure. Reviews are never written for the site. |
| The eight vehicle class pictures, 640×480 WebP with transparent backgrounds | `site/public/images/vehicle-classes/` | Served as they are at `/images/vehicle-classes/<file>`, on the booking form's photo cards. The same path goes in each class's photo card picture in the control app. They are third-party renders the owner chose knowing the business holds no license for them, so the public portfolio copy leaves them out ([decision 0104](../decisions/0104-portfolio-copy-leaves-out-unlicensed-pictures.md)). |
| The five category page photos | `site/src/assets/page-photos/` | Resized by Astro at build time, never shown larger than the original. |
| The hero, shine and reviews-background photos, the logo, the about and city photos, the sharing image and icons | `site/src/assets/` and `site/public/` | From the design canvas and the current site. |
| The Privacy Policy and Text Message Terms | `site/src/pages/privacy-policy.md` and `site/src/pages/sms-terms.md` | At `/privacy-policy/` and `/sms-terms/`, the addresses in [data/business.yaml](../../data/business.yaml) and the consent wording. The Privacy Policy's effective date is filled in at launch; the Text Message Terms keep the date on the live page. |

## How content stays current

The site shows the pricebook as it was when it was last built. Publishing a pricebook version in the control app calls the Cloudflare Pages deploy hook once the publish is saved (Bitwarden secret `CLOUDFLARE_PAGES_DEPLOY_HOOK`), so the new prices are live within a few minutes. A version published for a later date is picked up by `rebuild_website --if-due`, which runs every night at 2:20 AM with the public API cleanup and asks for a rebuild on the day a version takes effect. `python manage.py rebuild_website` asks for one by hand. Without the deploy hook nothing is asked for, and a failed call is logged without stopping a publish. A change to a data file reaches the site with the next build, which every merge to `main` starts. The booking flow itself always reads live prices from the public API.

## Speed and accessibility targets

Checked on every pull request that touches `site/` or `data/` by Lighthouse CI, on Lighthouse's phone emulation (a mid-range phone on a slow 4G connection), for the homepage, a service page, a city page, the questions and the booking page:

| Measure | Target |
| --- | --- |
| Performance score | 0.9 or more |
| Accessibility score | 0.95 or more |
| Best practices score | 0.9 or more |
| Largest contentful paint | 2.5 seconds or less |
| Cumulative layout shift | 0.1 or less |
| Total blocking time | 200 ms or less |

On 2026-11-18 every page scored 0.99 to 1.0 on performance and 1.0 on accessibility and best practices, with no layout shift and the largest paint at 1.2 to 2.2 seconds. The homepage is closest to the line, at about 2.2 seconds: its hero photo shares a slow connection with the font and the logo. Before that day it sat at 2.5 seconds and failed now and then. Three things keep its first screen light:

- **The font is trimmed.** The site serves Archivo cut to the weights (400 to 800), widths (condensed to normal) and characters it uses: 44 KB instead of 90. The list is `site/src/assets/fonts/archivo.json`, and `python3 tools/make_site_font.py` makes the font from it. A unit test fails when a built page uses a character outside the list: add the character and run the script again.
- **The stylesheet is inside each page,** so the first text needs no second request.
- **The hero photo has a 750-pixel size,** which a typical phone downloads instead of the 828.

Text shows at once in Arial sized to Archivo's width, so the swap to Archivo moves no line. Search-engine checks are left out while staging is deliberately not indexable.

## Staging is not indexed

Until the Phase 5 launch, `site/public/_headers` sends `X-Robots-Tag: noindex, nofollow` on every page and `site/public/robots.txt` disallows everything. The launch removes both, along with adding the redirects. Each page already carries its canonical `https://dixiedetail.com` address.

## Search ranking safeguards

- **No address breaks.** Every current address either stays or redirects permanently to its replacement; page titles and descriptions carry over.
- **Moved content stays indexed.** "How it works", the county detail, the questions and the reviews live on the services, city, FAQ and reviews pages.
- **Structured data comes from the database.** Business details, the service area, services and "from" prices are published as schema.org data (an auto wash business with its offers, each service, and the questions), built from the same pricebook as the page.
- **Speed improves.** Static pages on a global network load faster than WordPress pages built on request.
- **The Google Business Profile is untouched.**
- **Rollback is a DNS change.** WordPress stays intact through the cutover.

No redesign can guarantee rankings.
