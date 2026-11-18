// The site serves Archivo trimmed to the characters in
// src/assets/fonts/archivo.json (tools/make_site_font.py). A character
// outside them would show in the fallback font, so every character in the
// built pages and scripts must be in the list. Needs a build (dist/); it is
// skipped without one, as when the unit tests run on their own.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const dist = path.join(site, "dist");
const spec = JSON.parse(readFileSync(path.join(site, "src/assets/fonts/archivo.json"), "utf8"));
const ranges = spec.unicodes.map((item) => item.split("-").map((hex) => parseInt(hex, 16))).map(([low, high]) => [low, high ?? low]);
const covered = (code) => code < 0x20 || ranges.some(([low, high]) => code >= low && code <= high);

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? files(full) : [full];
  });
}

test("every character on the built pages is in the trimmed font", { skip: !existsSync(dist) && "no build in dist/" }, () => {
  const missing = new Map();
  for (const file of files(dist).filter((name) => /\.(html|js)$/.test(name))) {
    // Text only: scripts' JSON-LD and the like are never drawn in Archivo.
    const text = readFileSync(file, "utf8").replace(/<script type="application\/ld\+json">[\s\S]*?<\/script>/g, "");
    for (const char of text) {
      const code = char.codePointAt(0);
      if (!covered(code) && !missing.has(char)) missing.set(char, path.relative(dist, file));
    }
  }
  assert.deepEqual(
    [...missing].map(([char, file]) => `U+${char.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")} ${char} in ${file}`),
    [],
    "Add these to src/assets/fonts/archivo.json and run python3 tools/make_site_font.py",
  );
});
