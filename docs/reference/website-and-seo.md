---
title: Website and SEO
summary: The Astro website on Cloudflare Pages - its pages and addresses, where its text, photos and prices come from, how it stays current, the speed and accessibility targets, and the search-ranking safeguards for the launch.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-19
tags: [website, seo, design, astro, cloudflare, reviews, phase-3]
related: [docs/decisions/0109-reviews-kept-in-the-control-app.md, docs/guides/managing-website-reviews.md, docs/reference/booking-flow.md, docs/guides/previewing-and-deploying-the-website.md, docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/decisions/0002-astro-on-cloudflare.md, docs/decisions/0031-website-design-direction.md, docs/decisions/0104-portfolio-copy-leaves-out-unlicensed-pictures.md, data/site-content.yaml, data/site-pages.yaml, docs/reference/public-api.md]
---

# Website and SEO

The new website is a static Astro site in `site/`, on Cloudflare's free plan ([decision 0002](../decisions/0002-astro-on-cloudflare.md), [decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md)). It is built (Phase 3, Step 6) and runs on a staging address, kept out of search, until the Phase 5 launch replaces the WordPress site. The look follows the mockups approved on the design canvas "Dixie Detail Website Mockups" (https://claude.ai/artifact/SEu6MoMF3yauwcTDhuxwkL). How to preview and deploy it is in [../guides/previewing-and-deploying-the-website.md](../guides/previewing-and-deploying-the-website.md).

## Pages and addresses

Every address of the current site is kept, with its title and search description, so no link breaks and moved content keeps ranking.

| Address | Page | On the current site |
| --- | --- | --- |
| `/` | Homepage | Yes |
| `/services/` | "Mobile Detailing Services", under it "We come to your driveway in Bradley, McMinn, Hamilton, Polk, and Meigs Counties.", then four full-width sections, anchored `#detail`, `#correction`, `#headlight` and `#extraction`: each with its photo, its services' full descriptions (Motorcycle Detail with Premium Detailing) and the red box with its heading ("Book your detail today", "Book a paint correction", "Restore your headlights", "Book your detail today") and its button, "See my price" or "Add to detail". No price tables: the exact price shows on the booking page | Yes |
| `/services/detailing/`, `/services/paint-correction/`, `/services/headlight-restoration/`, `/services/shampoo-and-extraction/`, `/services/motorcycle-detail/` | The old category pages, redirected permanently (301) to their sections; `motorcycle-detail` goes to `#detail`. The build writes `_redirects` from `old_pages` in [data/site-content.yaml](../../data/site-content.yaml) | Redirected |
| `/cleveland-tn-mobile-detailing/`, `/athens-tn-mobile-detailing/`, `/chattanooga-tn-mobile-detailing/` | The city pages, headed "Mobile detailing in Cleveland TN" (Athens TN, Chattanooga TN) with "We'll come to your driveway anywhere in Bradley County." (McMinn, Hamilton) under it and no small label above (owner, 2026-11-19); where we work, the same four service cards as the homepage, reading and working the same, and their own questions | Yes |
| `/reviews/`, `/about/`, `/contact/` | Every shown review, on the plain white page of the other pages (no car photo behind it); the owner's story, headed "About Dixie Detail" with "An eye for perfection and a passion for quality" as a smaller subhead, laid out like the services and reviews pages; how to reach us, under "Have a question or comment? Call or text us and we'll get back to you right away." | Yes |
| `/faq/` | Every common question, the homepage's six included | New |
| `/book/` | The booking flow ([booking-flow.md](booking-flow.md)) | New |
| `/privacy-policy/`, `/sms-terms/` | The two policy pages, linked in the footer | Yes |

Every page but the homepage has the header photo (`site/src/assets/photos/page-header.webp`, 2026-11-18): it fills the whole header area, the menu bar and the page's heading, full width down to the red line, under a 50% black shade (`site/src/layouts/Base.astro`). Its crop ends at about the bottom edge of the nearest car's headlights, the photo's middle row, at every width and on a phone (owner, 2026-11-19; on WordPress the focal point was 20% from the top): the photo covers a box twice the header's height and only the box's top half shows.

Every address ends in a slash, as WordPress's do. The Phase 5 launch adds redirects for any other old address, such as WordPress's own feeds.

## Homepage structure

The homepage drops from nine sections to fewer, and the content that leaves moves to its own pages instead of being deleted, so each page can rank for its own search, such as "paint correction Cleveland TN". From the owner's direction (2026-10-10):

- The full-width hero photo with a 40% black shade, the script logo (larger than on other pages: 504 px wide on a desktop, 62% of a phone's width), the menu links on a translucent charcoal backing so they stay readable over the photo (72% opaque, 10% darker than at first, with the buttons' 10 px corners rather than a pill, owner 2026-11-19), and a "See your exact price" year, make and model picker, whose "See Price" button opens the booking flow with the vehicle filled in. On a phone the opened menu sits on top of the page, on the accent blue.
- A plain red band under the hero, with no text, the same thickness on phones.
- The "Restore the shine" section with its two side-by-side photos, a narrow column (400 px), and the three steps of how it works, each step's text in two lines on a desktop. The photos take the text's height, so the text is never taller than they are. No buttons under the text.
- "Services and pricing", with the subhead "We provide upfront pricing right here on our website. Pick your vehicle, see the exact price with tax, and pick a day that works for you. We show up and handle the rest.", and four service cards, 2 x 2 like the current dixiedetail.com: Premium Detailing, Paint Correction, Headlight Restoration and Shampoo & Extraction (motorcycles come under Premium Detailing). Each is light blue, with the owner's title and text (the card text of 2026-11-19), a white "from $xx" box (the lowest car and truck price of its services in the price book) and two buttons side by side: "See my price" or "Add to detail", to the booking page, and "More info", to its section of `/services/`. On a phone the buttons stack full width when they don't fit side by side. The cards and sections are `sections` in [data/site-content.yaml](../../data/site-content.yaml).
- Each card has its section's photo. From 1328 px wide up (where each card is 628 px wide) it is a square, 58% of the card's width, on the card's right side, full card height, behind the content, its outer corners following the card's rounding, with the description left-aligned entirely to its left; the heading, price box and buttons stay where they are. The photo's left edge fades into the card's blue, so a long heading that reaches it stays readable, and the outlined "More info" button is filled white over it. The description is 16 px there, which is what lets every card, the city pages' too, come out exactly square; checked by a browser test. Narrower, as on a phone, the text no longer fits beside a square, so the photo sits at the top of the card.
- The reviews section, just below the service cards, over the locked, non-scrolling background photo with a 50% shade (owner, 2026-11-19): up to three reviews, each with the name, the text and its stars when given, and the link to all the Google reviews. No combined rating figure. With none shown, it keeps only the link to Google.
- The service area (owner, 2026-11-19): "We come to you" with the five counties under it, and to its right the three city buttons, in the page's button shape, just above a Google map centered on Cleveland, with no marker, at zoom 9, just far enough out to take in Chattanooga, Athens, Decatur and Ocoee (`service_area.map` in [data/site-pages.yaml](../../data/site-pages.yaml)). On a phone the counties, the buttons and the map stack. The map is the Maps Embed API in view mode, which is free and draws no marker, with the browser key (`PUBLIC_GOOGLE_MAPS_BROWSER_KEY`; the key's API restrictions must include the Maps Embed API). It loads only as the visitor scrolls within 400 px of it, so it adds nothing to the first screen or the speed scores; until then its place holds a link to the same view on Google Maps. The frame has a title for screen readers. The Privacy Policy says the map may set Google's own cookies.
- Six common questions, in the owner's order (`home_faq` in [data/site-pages.yaml](../../data/site-pages.yaml), each also on `/faq/`): a shop to drop off at, what's needed on the day, stuff in the car, the glove box and console, a situation beyond a normal detail, and the prices, filled from the pricebook. Then a red call-to-action card, whose "Call or text" button stays on one line, and the charcoal footer with a red top edge.

Content is up to 1280 px wide, for 1920-wide screens.

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
| Page titles and descriptions, how it works, the counties, the map's view, the questions, the about page and the city pages | [data/site-pages.yaml](../../data/site-pages.yaml) | Carried over word for word from the current site, with the owner's later changes marked by date. Prices the pages write out are filled from the pricebook, such as `{from:Full Detail}`. |
| Customer reviews | The control app's Reviews screen, through `GET reviews` ([public-api.md](public-api.md#reviews-get-reviews)) | Read when the site is built, like prices ([decision 0109](../decisions/0109-reviews-kept-in-the-control-app.md)); a 404, from a server deployed before the endpoint existed, is read as none, with a warning in the build log. They are kept only in the database, so customers' names never enter this repository or its portfolio copy. Reviews are never written for the site. How to add one: [managing-website-reviews.md](../guides/managing-website-reviews.md). |
| The eight vehicle class pictures, 640×480 WebP with transparent backgrounds | `site/public/images/vehicle-classes/` | Served as they are at `/images/vehicle-classes/<file>`, on the booking form's photo cards. The same path goes in each class's photo card picture in the control app. They are third-party renders the owner chose knowing the business holds no license for them, so the public portfolio copy leaves them out ([decision 0104](../decisions/0104-portfolio-copy-leaves-out-unlicensed-pictures.md)). |
| The section photos, one per services page section, also on the homepage and city page service cards (`section_images` in [data/site-content.yaml](../../data/site-content.yaml); the detailing photo replaced 2026-11-18) | `site/src/assets/page-photos/` | Resized by Astro at build time, never shown larger than the original. |
| The hero, header, shine and reviews-background photos, the logo, the about and city photos, the sharing image and icons | `site/src/assets/` and `site/public/` | From the design canvas and the current site. |
| The Privacy Policy and Text Message Terms | `site/src/pages/privacy-policy.md` and `site/src/pages/sms-terms.md` | At `/privacy-policy/` and `/sms-terms/`, the addresses in [data/business.yaml](../../data/business.yaml) and the consent wording. Both take effect on the day the new site goes live, filled in at launch. They describe the one text consent (decision 0108): texts about a booked job, a review request after the service included, and no marketing texts. |

## How content stays current

The site shows the pricebook and the reviews as they were when it was last built. Publishing a pricebook version, or saving any change on the Reviews screen, in the control app calls the Cloudflare Pages deploy hook once the publish is saved (Bitwarden secret `CLOUDFLARE_PAGES_DEPLOY_HOOK`), so the new prices or reviews are live within a few minutes. A version published for a later date is picked up by `rebuild_website --if-due`, which runs every night at 2:20 AM with the public API cleanup and asks for a rebuild on the day a version takes effect. `python manage.py rebuild_website` asks for one by hand. Without the deploy hook nothing is asked for, and a failed call is logged without stopping a publish. A change to a data file reaches the site with the next build, which every merge to `main` starts. The booking flow itself always reads live prices from the public API.

## Speed and accessibility targets

Checked on every pull request that touches `site/` or `data/` by Lighthouse CI, on Lighthouse's phone emulation (a mid-range phone on a slow 4G connection), for the homepage, the services page, a city page, the questions, the booking page, the about, contact and reviews pages:

| Measure | Target |
| --- | --- |
| Performance score | 0.9 or more |
| Accessibility score | 0.95 or more |
| Best practices score | 0.9 or more |
| Largest contentful paint | 2.5 seconds or less |
| Cumulative layout shift | 0.1 or less |
| Total blocking time | 200 ms or less |

On 2026-11-19, after the third acceptance changes (the map, the reviews from the API, the longer card text), every page again scored 1.0 on performance, accessibility and best practices, with no layout shift and the largest paint at 1.5 to 1.9 seconds: the homepage 1.88 (185 KB, the same as before), a city page 1.8, services and booking 1.65, about 1.6, contact, the questions and reviews 1.5. On 2026-11-18, after the second acceptance changes and with the header photo, every page scored 1.0 on performance, accessibility and best practices, with no layout shift and the largest paint at 1.4 to 1.9 seconds: the homepage and a city page about 1.9, reviews 1.6, services and booking 1.7, about and contact 1.5, the questions 1.4. The homepage is closest to the line, at about 1.9 seconds, as before the changes: its hero photo shares a slow connection with the font and the logo. Before that day it sat at 2.5 seconds and failed now and then. These keep the first screens light:

- **The font is trimmed.** The site serves Archivo cut to the weights (400 to 800), widths (condensed to normal) and characters it uses: 44 KB instead of 90. The list is `site/src/assets/fonts/archivo.json`, and `python3 tools/make_site_font.py` makes the font from it. A unit test fails when a built page uses a character outside the list: add the character and run the script again.
- **The stylesheet is inside each page,** so the first text needs no second request.
- **The hero photo has a 750-pixel size,** which a typical phone downloads instead of the 828.
- **The larger logo and the menu backing add nothing to download.** On a typical phone the larger logo still loads the same 480-pixel file, and the backing is a style, not a picture.
- **The header photo is light and preloaded.** It comes in five sizes (480 to 1920 pixels) at a low quality, since the 50% shade hides the detail: a typical phone downloads the 750-pixel one, 38 KB.
- **The map waits.** The service area's Google map is written in only as the visitor scrolls near it, so the first screen and the speed scores never load it.
- **The service card photos wait.** The cards are laid out, and their photos fetched, only as they near the screen (`content-visibility: auto`), so on a phone the photos never share the connection with the hero. Without that the homepage's largest paint went from 1.9 to 2.0 seconds.

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
