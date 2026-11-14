---
title: Website and SEO
summary: The structure, design direction and search-ranking safeguards for the new Astro website that replaces WordPress at launch.
audience: [owner, developer]
visibility: internal
status: planned
updated: 2026-11-14
tags: [website, seo, design, astro, phase-3]
related: [docs/reference/booking-flow.md, docs/decisions/0002-astro-on-cloudflare.md, docs/decisions/0031-website-design-direction.md]
---

# Website and SEO

The new website will be a static Astro site on Cloudflare's free plan, built in Phase 3 on a staging address and switched on at launch in Phase 5. Homepage and booking-flow mockups were approved on the design canvas "Dixie Detail Website Mockups" (https://claude.ai/artifact/SEu6MoMF3yauwcTDhuxwkL).

## Homepage structure

The homepage drops from nine sections to fewer, and the content that leaves moves to its own pages instead of being deleted, so each page can rank for its own search, such as "paint correction Cleveland TN".

Kept from the current site, by the owner's direction (2026-10-10):

- The full-width hero photo with a 40% black shade and the script logo.
- A plain red band under the hero, with no text, the same thickness on phones.
- The "Make your vehicle shine" section with its two side-by-side photos; the text is free to change.
- The locked, non-scrolling background photo with a 50% shade, now behind the reviews section and placed after the "We come to you" section.

Also on the homepage: services with "from" prices read from the database, the service area, frequently asked questions with a red call-to-action card, and a charcoal footer with a red top edge.

## Colors and type

- Red #CC0000 is the base: buttons, the band under the hero, review cards and the call-to-action card.
- Navy #002D65 is the accent: small labels, prices, links, finished booking steps, and the booking estimate card and its phone bar.
- Headings are near-black. The footer is charcoal (#141518) with a red top edge.
- Footer social links are round logo icons (Facebook, X, Instagram, Google), not text. The Google icon links to the Google Business Profile review link in [data/business.yaml](../../data/business.yaml).

## Search ranking safeguards

- **No address breaks.** Every current address either stays or redirects permanently to its replacement; page titles and descriptions carry over.
- **Moved content stays indexed.** "How it works", the county detail, the questions and the reviews live on the services, city, FAQ and reviews pages.
- **Structured data comes from the database.** Business details, service area, services and prices are published in the format search engines read, and always match the page.
- **Speed improves.** Static pages on a global network load faster than WordPress pages built on request.
- **The Google Business Profile is untouched.**
- **Rollback is a DNS change.** WordPress stays intact through the cutover.

No redesign can guarantee rankings.

## Where the site's files are

The Astro project will live in `website/` in this repository. The owner's inputs for Phase 3, Step 6 are already in place:

| What | Where | How the site uses it |
| --- | --- | --- |
| Page and card text in the owner's words, the condition level cards, and which picture goes with each class and page | [data/site-content.yaml](../../data/site-content.yaml) | Read at build time. Service names match the price book; prices and times always come from the price book, never from this file. |
| The eight vehicle class pictures, 640×480 WebP with transparent backgrounds | `website/public/images/vehicle-classes/` | Served as they are at `/images/vehicle-classes/<file>`, the fixed path a class's photo card picture is set to in the control app, which the public API's photo cards return. |
| The five category page photos | `website/src/assets/page-photos/` | Resized by Astro's image tools at build time, never shown larger than the original. |
| The Privacy Policy and Text Message Terms | `website/src/pages/privacy-policy.md` and `website/src/pages/sms-terms.md` | Pages at `/privacy-policy/` and `/sms-terms/`, the addresses in [data/business.yaml](../../data/business.yaml) and the consent wording. The Privacy Policy's effective date is filled in at launch; the Text Message Terms keep the date on the live page. |
| The Google Business Profile review link | `google_business_profile` in [data/business.yaml](../../data/business.yaml) | The footer icon, the reviews page and, in Phase 4, review-request texts. |

The vehicle class pictures are third-party renders the owner chose knowing the business holds no license for them (noted in data/site-content.yaml). Replacing one means swapping its file under the same name.

## How content stays current

Service pages will get their prices and descriptions when the site is built. Publishing a pricebook change in the control app, which works since Phase 1, will also trigger a rebuild through a Cloudflare Pages deploy hook, live within a few minutes. The booking flow will always read live prices from the public API.
