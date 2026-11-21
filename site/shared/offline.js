// The Cloudflare offline piece's shared logic (decision 0100,
// docs/reference/public-api.md, offline requests), used by the Pages
// Function that takes a request from the website (functions/offline/) and
// the scheduled Worker that replays held ones (workers/offline-replay/).
//
// A held request is kept in Workers KV under "pending:<kind>:<request id>"
// for up to 14 days. Each replay is signed: X-Dixie-Timestamp (seconds) and
// X-Dixie-Signature, the hex HMAC-SHA256 of "<timestamp>.<raw body>" with
// OFFLINE_REQUESTS_SIGNING_KEY, the same Bitwarden secret the server holds.
// The website's request id makes a second replay harmless on the server.
//
// After each run the replay Worker reports to Healthchecks (decision 0114,
// report()): success when nothing is refused or stuck, the /fail URL when a
// request sits under "refused:" or has waited more than STUCK_AFTER while
// the server answers. A Worker that stops running stops pinging, which the
// check alerts on too. Only counts are logged or sent, never a request.

export const KINDS = {
  "time-request": "time-requests",
  "quote-request": "quote-requests/offline",
};
export const HOLD_SECONDS = 14 * 24 * 3600;
export const STUCK_AFTER = 3600 * 1000;
export const MAX_BYTES = 20000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function sign(key, raw, now = Date.now()) {
  const stamp = String(Math.floor(now / 1000));
  const cryptoKey = await crypto.subtle.importKey("raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(`${stamp}.${raw}`));
  const signature = [...new Uint8Array(mac)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return { "X-Dixie-Timestamp": stamp, "X-Dixie-Signature": signature };
}

// Send one request to the server, signed. Returns "sent" (2xx), "refused"
// (a 4xx the server will refuse again: kept aside for the owner),
// "unsigned" (401: the signing key is wrong; keep holding), or "down".
export async function deliver(env, kind, body, fetcher = fetch) {
  const raw = JSON.stringify(body);
  let response;
  try {
    response = await fetcher(`${env.API_BASE.replace(/\/$/, "")}/${KINDS[kind]}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "User-Agent": "dixie-detail-offline", ...(await sign(env.OFFLINE_REQUESTS_SIGNING_KEY, raw)) },
      body: raw,
    });
  } catch {
    return { result: "down" };
  }
  if (response.ok) return { result: "sent", status: response.status };
  if (response.status === 401) return { result: "unsigned", status: 401 };
  if (response.status === 429 || response.status >= 500) return { result: "down", status: response.status };
  return { result: "refused", status: response.status, detail: (await response.text()).slice(0, 2000) };
}

export function check(kind, body) {
  if (!KINDS[kind]) return "That form isn't taken here.";
  if (!body || typeof body !== "object" || Array.isArray(body)) return "The form didn't arrive whole. Please try again.";
  if (!UUID.test(String(body.request_id || ""))) return "The form didn't arrive whole. Please try again.";
  if (typeof body.turnstile !== "string" || !body.turnstile) return "We couldn't confirm you're a person. Please try again.";
  return null;
}

export async function turnstileOk(env, token, ip, fetcher = fetch) {
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET_KEY);
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  try {
    const response = await fetcher("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    return (await response.json()).success === true;
  } catch {
    return false;
  }
}

export const pendingKey = (kind, id) => `pending:${kind}:${id}`;
export const refusedKey = (kind, id) => `refused:${kind}:${id}`;

// The time it was held goes in the key's metadata too, so a run can see how
// long each has waited from the key list alone.
export async function holdRequest(env, kind, body, now = Date.now()) {
  const held_at = new Date(now).toISOString();
  await env.OFFLINE_REQUESTS.put(pendingKey(kind, body.request_id), JSON.stringify({ kind, body, held_at }), { expirationTtl: HOLD_SECONDS, metadata: { held_at } });
}

// Replay every held request, in key order, stopping at the first sign the
// server is still down so a long outage costs few calls. Returns counts, and
// in waiting the keys still held, with their metadata, for report().
export async function replay(env, fetcher = fetch, log = console) {
  const counts = { sent: 0, refused: 0, held: 0, waiting: [] };
  let cursor;
  do {
    const page = await env.OFFLINE_REQUESTS.list({ prefix: "pending:", cursor });
    for (const [index, { name }] of page.keys.entries()) {
      const stored = await env.OFFLINE_REQUESTS.get(name, "json");
      if (!stored) continue;
      const outcome = await deliver(env, stored.kind, stored.body, fetcher);
      if (outcome.result === "sent") {
        await env.OFFLINE_REQUESTS.delete(name);
        counts.sent++;
      } else if (outcome.result === "refused") {
        // Never lost: kept aside for the owner to read, with the server's answer.
        await env.OFFLINE_REQUESTS.put(refusedKey(stored.kind, stored.body.request_id), JSON.stringify({ ...stored, status: outcome.status, answer: outcome.detail }), { expirationTtl: HOLD_SECONDS * 2 });
        await env.OFFLINE_REQUESTS.delete(name);
        log.error(`An offline ${stored.kind} was refused by the server: HTTP ${outcome.status}.`);
        counts.refused++;
      } else {
        if (outcome.result === "unsigned") log.error("The server refused the signature: check OFFLINE_REQUESTS_SIGNING_KEY matches Bitwarden.");
        // This one and the rest of the page wait for the next run.
        counts.held += page.keys.length - index;
        counts.waiting.push(...page.keys.slice(index));
        return counts;
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return counts;
}

// When a held request was held: from its key's metadata, or, for one held
// before the metadata was added, from the stored value.
async function heldAt(env, key) {
  if (key.metadata && key.metadata.held_at) return Date.parse(key.metadata.held_at);
  const stored = await env.OFFLINE_REQUESTS.get(key.name, "json");
  return stored && stored.held_at ? Date.parse(stored.held_at) : NaN;
}

// Whether the server answers: its /health page, beside the public API.
export async function serverAnswers(env, fetcher = fetch) {
  try {
    const response = await fetcher(new URL("/health", env.API_BASE).toString(), { headers: { "User-Agent": "dixie-detail-offline" } });
    return response.ok;
  } catch {
    return false;
  }
}

// After a run: how many requests are refused (kept under "refused:" for the
// owner) and how many are stuck (held more than STUCK_AFTER while the server
// answers). The server is asked only when something old is still held.
export async function status(env, counts, fetcher = fetch, now = Date.now()) {
  const refused = (await env.OFFLINE_REQUESTS.list({ prefix: "refused:" })).keys.length;
  let stuck = 0;
  const old = [];
  for (const key of counts.waiting || []) {
    if (now - (await heldAt(env, key)) > STUCK_AFTER) old.push(key);
  }
  if (old.length && (await serverAnswers(env, fetcher))) stuck = old.length;
  return { sent: counts.sent, refused, held: counts.held, stuck };
}

// Ping the Healthchecks check HEALTHCHECKS_OFFLINE_URL (a Worker secret):
// success, or /fail when anything is refused or stuck. The body carries the
// counts only.
export async function report(env, summary, fetcher = fetch, log = console) {
  const ok = summary.refused === 0 && summary.stuck === 0;
  const line = `sent=${summary.sent} refused=${summary.refused} held=${summary.held} stuck=${summary.stuck}`;
  if (!env.HEALTHCHECKS_OFFLINE_URL) {
    log.error("HEALTHCHECKS_OFFLINE_URL is not set, so this run was not reported.");
    return ok;
  }
  const url = env.HEALTHCHECKS_OFFLINE_URL.replace(/\/$/, "") + (ok ? "" : "/fail");
  try {
    await fetcher(url, { method: "POST", body: line, headers: { "User-Agent": "dixie-detail-offline" } });
  } catch {
    log.error("Healthchecks couldn't be reached.");
  }
  return ok;
}
