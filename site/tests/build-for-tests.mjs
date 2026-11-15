// Build the site against the fake API (tests/fake/api.mjs), with Turnstile
// and Google's address suggestions pointed at the local fakes, for the
// browser tests and the Lighthouse checks. Then `npm run preview` serves it.
import { spawn } from "node:child_process";

const port = process.env.PORT || "4321";
const origin = `http://127.0.0.1:${port}`;
const fake = spawn(process.execPath, ["tests/serve.mjs"], { env: { ...process.env, PORT: port, FAKE_ONLY: "1" }, stdio: ["ignore", "pipe", "inherit"] });
await new Promise((resolve) => fake.stdout.once("data", resolve));
const env = {
  ...process.env,
  API_BASE: `${origin}/api/public/v1`,
  PUBLIC_API_BASE: `${origin}/api/public/v1`,
  PUBLIC_OFFLINE_BASE: "/offline",
  PUBLIC_TURNSTILE_SITE_KEY: "fake-site-key",
  PUBLIC_TURNSTILE_SCRIPT: "/__fake/turnstile.js",
  PUBLIC_PLACES_ENDPOINT: "/__fake/places:autocomplete",
  PUBLIC_GOOGLE_MAPS_BROWSER_KEY: "fake-browser-key",
};
const build = spawn("npx", ["astro", "build"], { env, stdio: "inherit" });
const code = await new Promise((resolve) => build.on("exit", resolve));
fake.kill();
process.exit(code);
