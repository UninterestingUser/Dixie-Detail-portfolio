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
  build: { format: "directory", inlineStylesheets: "auto" },
  compressHTML: true,
  image: { responsiveStyles: false },
  integrations: [requiredSettings],
});
