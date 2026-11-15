// Checks that no price is computed in the browser (decision 0059): every
// amount the booking flow shows is the server's text, shown as it is. Run
// by CI with the browser tests, which also prove it from the other side (a
// fake server whose totals are not the sums of their lines).
//
// In every browser script (src/scripts/ and <script> blocks in src/), it
// refuses:
// - turning text into a number: parseFloat, parseInt, Number(...), toFixed;
// - arithmetic on anything named like money: price, total, amount, tax,
//   cents, dollars, subtotal.
// A line that converts or counts something else, such as an id or a step
// number, says so with a "// not money: why" note, so each exception is
// visible in review.

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const MONEY = /\b\w*(price|total|amount|tax|cents|dollar|subtotal)\w*\b/i;
const CONVERT = /\b(parseFloat|parseInt|toFixed)\b|\bNumber\s*\(/;
const ARITHMETIC = /[\w)\]]\s*[-+*/%]\s*[\w(]|[-+*/%]=|\+\+|--/;

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? files(full) : [full];
  });
}

// The browser code in a file: a whole .js file under scripts/, or the
// <script> blocks of an .astro file (not its build-time frontmatter).
function browserCode(file) {
  const text = readFileSync(file, "utf8");
  if (file.endsWith(".js")) return file.includes(`${path.sep}scripts${path.sep}`) ? text : "";
  if (!file.endsWith(".astro")) return "";
  return [...text.matchAll(/<script(?![^>]*type="application\/(ld\+)?json")[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[2]).join("\n");
}

const problems = [];
for (const file of files(root)) {
  const code = browserCode(file);
  if (!code) continue;
  const relative = path.relative(root, file);
  code.split("\n").forEach((line, index) => {
    if (/\/\/ not money: \S/.test(line)) return;
    const bare = line.replace(/\/\/.*$/, "").replace(/(["'`])(?:\\.|(?!\1).)*\1/g, '""');
    if (!bare.trim()) return;
    if (CONVERT.test(bare)) {
      problems.push(`${relative}:${index + 1}: turns text into a number: ${line.trim()}`);
    }
    if (MONEY.test(bare) && ARITHMETIC.test(bare.replace(/=>/g, "").replace(/\?\./g, "."))) {
      problems.push(`${relative}:${index + 1}: arithmetic beside a money name: ${line.trim()}`);
    }
  });
}

if (problems.length) {
  console.error(`No price may be computed in the browser (decision 0059). ${problems.length} problem(s):`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}
console.log("No price is computed in the browser.");
