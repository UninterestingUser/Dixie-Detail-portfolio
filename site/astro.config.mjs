// The Dixie Detail website (docs/reference/website-and-seo.md): static
// pages for Cloudflare Pages. Every address ends in a slash, like the
// WordPress site it replaces, so no current address breaks.
import { defineConfig } from "astro/config";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { checkSettings } from "./src/lib/settings.js";
import { redirectLines } from "./src/lib/redirects.js";

// The repository's data/ folder, worked out here because this file isn't
// bundled. Astro 7 bundles the pages into dist/.prerender/ before rendering
// them, so a path relative to a page's own file no longer reaches data/;
// src/lib/data.js reads this variable first.
process.env.DIXIE_DATA_DIR ||= fileURLToPath(new URL("../data/", import.meta.url));

// A build stops at once when a required setting is empty (src/lib/settings.js).
const requiredSettings = {
  name: "dixie-required-settings",
  hooks: { "astro:build:start": () => checkSettings() },
};

// The old category pages redirect to their sections of /services/
// (src/lib/redirects.js), written beside the pages after each build.
const redirects = {
  name: "dixie-redirects",
  hooks: {
    "astro:build:done": ({ dir }) => {
      const data = process.env.DIXIE_DATA_DIR;
      const content = parse(readFileSync(`${data}/site-content.yaml`, "utf8"));
      writeFileSync(new URL("_redirects", dir), redirectLines(content.sections));
    },
  },
};

export default defineConfig({
  site: "https://dixiedetail.com",
  trailingSlash: "always",
  // The stylesheet is inside each page, so the first text needs no second
  // request on a slow connection (about 150 ms sooner on a phone).
  build: { format: "directory", inlineStylesheets: "always" },
  compressHTML: true,
  image: { responsiveStyles: false },
  integrations: [requiredSettings, redirects],
});
