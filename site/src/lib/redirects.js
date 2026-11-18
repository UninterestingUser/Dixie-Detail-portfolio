// Cloudflare Pages redirects (dist/_redirects), from data/site-content.yaml:
// each old category page, such as /services/detailing/, goes permanently to
// its section of the one services page, /services/#detail. Both spellings,
// with and without the final slash, are listed.

export function redirectLines(sections) {
  const lines = ["# Made at build time from data/site-content.yaml (src/lib/redirects.js)."];
  for (const section of sections) {
    for (const slug of section.old_pages || []) {
      for (const from of [`/services/${slug}/`, `/services/${slug}`]) lines.push(`${from} /services/#${section.anchor} 301`);
    }
  }
  return lines.join("\n") + "\n";
}

// [from, to, status] rules from a _redirects file's text.
export function parseRedirects(text) {
  return text.split("\n").map((line) => line.trim()).filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split(/\s+/)).map(([from, to, status]) => [from, to, Number(status || 302)]); // not money: an HTTP status
}
