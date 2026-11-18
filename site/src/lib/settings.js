// The site's build settings (website_build_settings in data/configuration.yaml).
// A setting the site can't work without stops the build with a message that
// names it, instead of going out with an empty value: an empty Turnstile site
// key, for one, leaves every form unable to send.

export const REQUIRED = [
  ["API_BASE", "the public API's address, such as https://api.dixiedetail.com/api/public/v1"],
  ["PUBLIC_TURNSTILE_SITE_KEY", "the Turnstile widget's site key"],
  ["PUBLIC_GOOGLE_MAPS_BROWSER_KEY", "the Google Maps browser key"],
];

// The names of required settings that are missing or blank in env.
export function missingSettings(env = process.env) {
  return REQUIRED.filter(([name]) => !String(env[name] ?? "").trim()).map(([name]) => name);
}

// Throws one error listing every missing setting, or returns nothing.
export function checkSettings(env = process.env) {
  const missing = missingSettings(env);
  if (!missing.length) return;
  const lines = REQUIRED.filter(([name]) => missing.includes(name)).map(([name, what]) => `  ${name}: ${what}`);
  throw new Error(
    `The site build needs these settings, and they are empty:\n${lines.join("\n")}\n` +
      "On Cloudflare Pages, set them under Settings, Variables and Secrets, as type Text " +
      "(docs/guides/previewing-and-deploying-the-website.md, step 3).",
  );
}

// A required setting's value, trimmed. Call checkSettings first.
export function setting(name, env = process.env) {
  const value = String(env[name] ?? "").trim();
  if (!value) checkSettings(env);
  return value;
}

// The API address the browser calls: PUBLIC_API_BASE when set (the test
// build), otherwise API_BASE, without a trailing slash.
export function browserApiBase(env = process.env) {
  return (String(env.PUBLIC_API_BASE ?? "").trim() || setting("API_BASE", env)).replace(/\/+$/, "");
}
