// The build's required settings (src/lib/settings.js): an empty one stops
// the build with a message that names it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { browserApiBase, checkSettings, missingSettings } from "../../src/lib/settings.js";

const full = {
  API_BASE: "https://api.example.com/api/public/v1",
  PUBLIC_TURNSTILE_SITE_KEY: "0x4AAAAexample",
  PUBLIC_GOOGLE_MAPS_BROWSER_KEY: "AIzaExample",
};

test("every required setting present: nothing missing", () => {
  assert.deepEqual(missingSettings(full), []);
  assert.doesNotThrow(() => checkSettings(full));
});

test("an empty or blank setting is missing, and the message names it", () => {
  const env = { ...full, PUBLIC_TURNSTILE_SITE_KEY: "", PUBLIC_GOOGLE_MAPS_BROWSER_KEY: "   " };
  assert.deepEqual(missingSettings(env), ["PUBLIC_TURNSTILE_SITE_KEY", "PUBLIC_GOOGLE_MAPS_BROWSER_KEY"]);
  assert.throws(() => checkSettings(env), (error) => {
    assert.match(error.message, /PUBLIC_TURNSTILE_SITE_KEY: the Turnstile widget's site key/);
    assert.match(error.message, /PUBLIC_GOOGLE_MAPS_BROWSER_KEY/);
    assert.doesNotMatch(error.message, /API_BASE:/);
    return true;
  });
});

test("an unset API address stops the build", () => {
  const { API_BASE, ...env } = full;
  assert.deepEqual(missingSettings(env), ["API_BASE"]);
  assert.throws(() => browserApiBase(env), /API_BASE: the public API's address/);
});

test("the browser's API address prefers PUBLIC_API_BASE and drops a trailing slash", () => {
  assert.equal(browserApiBase({ ...full, API_BASE: "https://api.example.com/api/public/v1/" }), "https://api.example.com/api/public/v1");
  assert.equal(browserApiBase({ ...full, PUBLIC_API_BASE: "http://127.0.0.1:4321/api/public/v1" }), "http://127.0.0.1:4321/api/public/v1");
});
