// Lighthouse CI: speed and accessibility on a phone (Lighthouse's default
// mobile emulation, a mid-range phone on a slow 4G connection), against the
// test build and the fake API. The targets (website-and-seo.md):
//   performance score >= 0.9, accessibility >= 0.95, best practices >= 0.9,
//   largest contentful paint <= 2.5 s, layout shift <= 0.1,
//   total blocking time <= 200 ms.
// Search-engine checks are left out: staging is deliberately not indexable.
const { chromium } = require("@playwright/test");

module.exports = {
  ci: {
    collect: {
      startServerCommand: "node tests/serve.mjs",
      startServerReadyPattern: "serving on",
      url: ["/", "/services/", "/cleveland-tn-mobile-detailing/", "/faq/", "/book/", "/about/", "/contact/", "/reviews/"].map((path) => `http://127.0.0.1:4321${path}`),
      numberOfRuns: 3,
      chromePath: process.env.CHROME_PATH || chromium.executablePath(),
      settings: { chromeFlags: "--no-sandbox --headless=new" },
    },
    assert: {
      assertions: {
        "categories:performance": ["error", { minScore: 0.9, aggregationMethod: "median-run" }],
        "categories:accessibility": ["error", { minScore: 0.95, aggregationMethod: "median-run" }],
        "categories:best-practices": ["error", { minScore: 0.9, aggregationMethod: "median-run" }],
        "largest-contentful-paint": ["error", { maxNumericValue: 2500, aggregationMethod: "median-run" }],
        "cumulative-layout-shift": ["error", { maxNumericValue: 0.1, aggregationMethod: "median-run" }],
        "total-blocking-time": ["error", { maxNumericValue: 200, aggregationMethod: "median-run" }],
      },
    },
    upload: { target: "filesystem", outputDir: ".lighthouseci" },
  },
};
