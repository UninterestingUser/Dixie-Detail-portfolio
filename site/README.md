# The Dixie Detail website

A static Astro site for Cloudflare Pages, with its booking flow and Cloudflare's offline piece. What it is and why: [docs/reference/website-and-seo.md](../docs/reference/website-and-seo.md), [docs/reference/booking-flow.md](../docs/reference/booking-flow.md) and [decision 0105](../docs/decisions/0105-the-website-on-cloudflare-pages.md). How to preview, test and deploy it: [docs/guides/previewing-and-deploying-the-website.md](../docs/guides/previewing-and-deploying-the-website.md).

```bash
npm ci
npm run build:test && npm run preview   # the whole site against a fake API, at http://127.0.0.1:4321
npm test                                # no prices in the browser, the offline piece, the booking flow in a browser
npm run test:lighthouse                 # speed and accessibility on a phone
```

| Folder | What is in it |
| --- | --- |
| `src/pages/` | One file per page or set of pages; `book.astro` is the booking page |
| `src/scripts/booking/` | The booking flow, run in the browser. It never works a price out: `npm run check:prices` checks |
| `src/lib/` | Build-time data: the repository's `data/` files and the public API |
| `src/components/`, `src/layouts/`, `src/styles/` | Shared pieces and the look, from the approved mockups |
| `src/assets/`, `public/` | Photos (resized at build time), the class pictures at fixed addresses, icons, `_headers` and `robots.txt` |
| `functions/offline/` | The Cloudflare Pages Function that takes offline forms |
| `workers/offline-replay/` | The scheduled Worker that replays held offline requests |
| `shared/` | Signing, holding and replaying, shared by the two |
| `tests/` | The fake API and test server, the browser tests, the unit tests (the offline piece, the required settings, and the fake API against the real API's shapes in `data/public-api-shapes.yaml`) and the price check |
