// The Dixie Detail website (docs/reference/website-and-seo.md): static
// pages for Cloudflare Pages. Every address ends in a slash, like the
// WordPress site it replaces, so no current address breaks.
import { defineConfig } from "astro/config";
import { checkSettings } from "./src/lib/settings.js";

// A build stops at once when a required setting is empty (src/lib/settings.js).
const requiredSettings = {
  name: "dixie-required-settings",
  hooks: { "astro:build:start": () => checkSettings() },
};

export default defineConfig({
  site: "https://dixiedetail.com",
  trailingSlash: "always",
  // The stylesheet is inside each page, so the first text needs no second
  // request on a slow connection (about 150 ms sooner on a phone).
  build: { format: "directory", inlineStylesheets: "always" },
  compressHTML: true,
  image: { responsiveStyles: false },
  integrations: [requiredSettings],
});
