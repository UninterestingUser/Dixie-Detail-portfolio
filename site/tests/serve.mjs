// Serve the built site (dist/) with the fake API, the offline piece and fake
// Turnstile and Google address suggestions, all on one local port, for the
// browser tests and for previewing a build without the server:
//
//   API_BASE=http://127.0.0.1:4321/api/public/v1 ... npm run build   (see tests/build-for-tests.mjs)
//   npm run preview        then open http://127.0.0.1:4321
//
// With FAKE_ONLY=1 it serves only the fakes (for the build step).

import { createServer } from "node:http";
import { gzipSync } from "node:zlib";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createFakeApi, GOOD_TOKEN, PLACES } from "./fake/api.mjs";
import { parseRedirects } from "../src/lib/redirects.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(here, "../dist");
const port = Number(process.env.PORT || 4321);
const fake = createFakeApi();

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain", ".xml": "application/xml" };

// Turnstile's script, as the site uses it: render() with execution
// "execute", then execute() calls back with a token. localStorage
// "fake-turnstile" makes it misbehave as the real one can: "throw" (render
// throws, as with an empty site key), "fail" (the error callback), "hang"
// (no answer ever), "hang-once" (no answer to the first check only, as when
// a first photo upload sat on "Uploading") or "empty" (a blank token).
// window.fakeTurnstileChecks counts the checks.
const TURNSTILE = `window.turnstile = {
  render(el, options) {
    if (localStorage.getItem("fake-turnstile") === "throw") throw new Error('Invalid input for parameter "sitekey", got ""');
    this.options = options; return "widget-1";
  },
  execute() {
    const mode = localStorage.getItem("fake-turnstile");
    window.fakeTurnstileChecks = (window.fakeTurnstileChecks || 0) + 1;
    if (mode === "hang") return;
    if (mode === "hang-once" && window.fakeTurnstileChecks === 1) return;
    setTimeout(() => mode === "fail" ? this.options["error-callback"]?.() : this.options.callback(mode === "empty" ? "" : "${GOOD_TOKEN}"), 10);
  },
  reset() {}, remove() {}
};
(window.onTurnstileLoad || function () {})();`;

async function places(req, res) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (fake.state.mode.outage) { res.writeHead(429, { "Content-Type": "application/json" }); return res.end('{"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}'); }
  const { input } = JSON.parse(Buffer.concat(chunks).toString() || "{}");
  const words = String(input || "").toLowerCase().split(/[\s,]+/).filter(Boolean);
  const suggestions = Object.entries(PLACES)
    .filter(([, p]) => words.every((w) => `${p.line1} ${p.city} ${p.state}`.toLowerCase().split(/[\s,]+/).some((h) => h.startsWith(w))))
    .map(([placeId, p]) => ({ placePrediction: { placeId, text: { text: `${p.line1}, ${p.city}, ${p.state}, USA` }, structuredFormat: { mainText: { text: p.line1 }, secondaryText: { text: `${p.city}, ${p.state}, USA` } } } }));
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ suggestions }));
}

// Cloudflare Pages' redirects, from the build's _redirects file.
async function redirect(res, pathname) {
  let rules = [];
  try { rules = parseRedirects(await readFile(path.join(dist, "_redirects"), "utf8")); } catch { return false; }
  const rule = rules.find(([from]) => from === pathname);
  if (!rule) return false;
  res.writeHead(rule[2], { Location: rule[1] });
  res.end();
  return true;
}

async function file(res, pathname) {
  let target = path.join(dist, decodeURIComponent(pathname));
  if (!target.startsWith(dist)) { res.writeHead(403); return res.end(); }
  try {
    if ((await stat(target)).isDirectory()) target = path.join(target, "index.html");
  } catch { target = path.join(dist, "404.html"); res.statusCode = 404; }
  try {
    let body = await readFile(target);
    const type = TYPES[path.extname(target)] || "application/octet-stream";
    res.setHeader("Content-Type", type);
    // Compressed like Cloudflare compresses it, so the speed checks see
    // what a visitor's phone gets.
    if (/text|javascript|json|xml|svg/.test(type)) {
      body = gzipSync(body);
      res.setHeader("Content-Encoding", "gzip");
    }
    if (pathname.startsWith("/_astro/")) res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
    res.end(body);
  } catch { res.writeHead(404); res.end("Not found"); }
}

createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://local");
  if (pathname === "/__fake/turnstile.js") { res.writeHead(200, { "Content-Type": "text/javascript" }); return res.end(TURNSTILE); }
  if (pathname === "/__fake/places:autocomplete") return places(req, res);
  const handled = await fake.handle(req, res);
  if (handled !== false) return;
  if (process.env.FAKE_ONLY) { res.writeHead(404); return res.end(); }
  if (await redirect(res, pathname)) return;
  return file(res, pathname);
}).listen(port, "127.0.0.1", () => console.log(`serving on http://127.0.0.1:${port}`));
