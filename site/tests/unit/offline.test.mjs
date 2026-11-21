// The Cloudflare offline piece: signing, holding, and replaying.
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { onRequestPost } from "../../functions/offline/[kind].js";
import { deliver, holdRequest, replay, report, sign, status, STUCK_AFTER } from "../../shared/offline.js";
import { run } from "../../workers/offline-replay/index.js";

const KEY = "made-up-offline-signing-key-for-tests";
const ID = "0b9f1d5e-4c1a-4a6b-9f0e-2d3c4b5a6978";

function kv() {
  const store = new Map();
  return {
    store,
    meta: new Map(),
    lists: 0,
    async put(key, value, options = {}) { store.set(key, value); if (options.metadata) this.meta.set(key, options.metadata); },
    async get(key, type) { const value = store.get(key); return value && type === "json" ? JSON.parse(value) : value ?? null; },
    async delete(key) { store.delete(key); this.meta.delete(key); },
    async list({ prefix }) {
      this.lists++;
      return { keys: [...store.keys()].filter((k) => k.startsWith(prefix)).sort().map((name) => ({ name, ...(this.meta.has(name) ? { metadata: this.meta.get(name) } : {}) })), list_complete: true };
    },
  };
}

const env = () => ({ API_BASE: "https://api.example.test/api/public/v1", OFFLINE_REQUESTS_SIGNING_KEY: KEY, TURNSTILE_SECRET_KEY: "secret", OFFLINE_REQUESTS: kv() });

test("the signature is the server's: HMAC-SHA256 of timestamp.body", async () => {
  const raw = JSON.stringify({ request_id: ID });
  const headers = await sign(KEY, raw, 1_800_000_000_000);
  assert.equal(headers["X-Dixie-Timestamp"], "1800000000");
  const expected = createHmac("sha256", KEY).update(`1800000000.${raw}`).digest("hex");
  assert.equal(headers["X-Dixie-Signature"], expected);
});

test("deliver reads the server's answer", async () => {
  const answer = (status) => async () => new Response("{}", { status });
  assert.equal((await deliver(env(), "time-request", { request_id: ID }, answer(201))).result, "sent");
  assert.equal((await deliver(env(), "time-request", { request_id: ID }, answer(422))).result, "refused");
  assert.equal((await deliver(env(), "time-request", { request_id: ID }, answer(401))).result, "unsigned");
  assert.equal((await deliver(env(), "time-request", { request_id: ID }, answer(502))).result, "down");
  assert.equal((await deliver(env(), "time-request", { request_id: ID }, async () => { throw new Error("no route"); })).result, "down");
});

function post(kind, body) {
  return { request: new Request("https://site.test/offline/" + kind, { method: "POST", body: JSON.stringify(body), headers: { "CF-Connecting-IP": "198.51.100.7" } }), params: { kind } };
}

test("the function checks Turnstile, tries the server, and holds the request when it is down", async (t) => {
  const e = env();
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push(String(url));
    if (String(url).includes("siteverify")) return new Response(JSON.stringify({ success: true }));
    throw new Error("server down");
  });
  const response = await onRequestPost({ ...post("time-request", { request_id: ID, turnstile: "token", first_name: "Jordan" }), env: e });
  assert.equal(response.status, 202);
  const held = JSON.parse(e.OFFLINE_REQUESTS.store.get(`pending:time-request:${ID}`));
  assert.equal(held.body.first_name, "Jordan");
  assert.equal(held.body.turnstile, undefined, "the token is not kept");
  assert.ok(calls[1].endsWith("/time-requests"));
});

test("the function sends at once when the server is up, holding nothing", async (t) => {
  const e = env();
  t.mock.method(globalThis, "fetch", async (url) => new Response(JSON.stringify({ success: true }), { status: String(url).includes("siteverify") ? 200 : 201 }));
  const response = await onRequestPost({ ...post("quote-request", { request_id: ID, turnstile: "token" }), env: e });
  assert.equal(response.status, 202);
  assert.equal(e.OFFLINE_REQUESTS.store.size, 0);
});

test("a failed Turnstile check or a malformed form is refused and nothing is held", async (t) => {
  const e = env();
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ success: false })));
  assert.equal((await onRequestPost({ ...post("time-request", { request_id: ID, turnstile: "bad" }), env: e })).status, 403);
  assert.equal((await onRequestPost({ ...post("time-request", { request_id: "nope", turnstile: "t" }), env: e })).status, 400);
  assert.equal((await onRequestPost({ ...post("bookings", { request_id: ID, turnstile: "t" }), env: e })).status, 400);
  assert.equal(e.OFFLINE_REQUESTS.store.size, 0);
});

test("the replay sends each held request, keeps a refused one aside, and stops while the server is down", async () => {
  const e = env();
  const second = "1b9f1d5e-4c1a-4a6b-9f0e-2d3c4b5a6978";
  await e.OFFLINE_REQUESTS.put(`pending:time-request:${ID}`, JSON.stringify({ kind: "time-request", body: { request_id: ID } }));
  await e.OFFLINE_REQUESTS.put(`pending:time-request:${second}`, JSON.stringify({ kind: "time-request", body: { request_id: second } }));
  const quiet = { error() {} };
  let counts = await replay(e, async () => new Response("", { status: 503 }), quiet);
  assert.deepEqual({ ...counts, waiting: counts.waiting.length }, { sent: 0, refused: 0, held: 2, waiting: 2 });
  counts = await replay(e, async (url, options) => new Response("{}", { status: JSON.parse(options.body).request_id === ID ? 201 : 400 }), quiet);
  assert.deepEqual(counts, { sent: 1, refused: 1, held: 0, waiting: [] });
  assert.deepEqual([...e.OFFLINE_REQUESTS.store.keys()], [`refused:time-request:${second}`]);
});

// The health report (decision 0114) ------------------------------------------

const HOUR = 3600 * 1000;
const quietLog = { error() {}, log() {} };

function healthEnv() {
  return { ...env(), HEALTHCHECKS_OFFLINE_URL: "https://hc-ping.example.test/made-up-check" };
}

// A server that answers /health with health, and every request with request.
function server({ health = 200, request = 201, pings }) {
  return async (url, options = {}) => {
    const address = String(url);
    if (address.startsWith("https://hc-ping.example.test")) {
      pings.push({ url: address, body: options.body });
      return new Response("OK");
    }
    if (address.endsWith("/health")) {
      if (health === null) throw new Error("no route");
      return new Response("ok", { status: health });
    }
    return new Response("{}", { status: request });
  };
}

test("a held request keeps when it was held in its key's metadata", async () => {
  const e = env();
  await holdRequest(e, "time-request", { request_id: ID }, Date.parse("2026-11-21T12:00:00Z"));
  assert.deepEqual(e.OFFLINE_REQUESTS.meta.get(`pending:time-request:${ID}`), { held_at: "2026-11-21T12:00:00.000Z" });
});

test("a clean run pings success, with only the counts", async () => {
  const e = healthEnv();
  await holdRequest(e, "time-request", { request_id: ID, first_name: "Jordan", mobile: "4235550142" });
  const pings = [];
  const logged = [];
  const summary = await run(e, server({ pings }), { error: (line) => logged.push(line), log: (line) => logged.push(line) });
  assert.deepEqual(summary, { sent: 1, refused: 0, held: 0, stuck: 0 });
  assert.deepEqual(pings, [{ url: "https://hc-ping.example.test/made-up-check", body: "sent=1 refused=0 held=0 stuck=0" }]);
  assert.ok(!logged.join(" ").includes("Jordan") && !logged.join(" ").includes("4235550142"), "no request contents are logged");
  assert.ok(!pings[0].body.includes("Jordan"));
});

test("a refused request makes the check fail until it is dealt with", async () => {
  const e = healthEnv();
  await holdRequest(e, "time-request", { request_id: ID });
  const pings = [];
  await run(e, server({ request: 400, pings }), quietLog);
  assert.equal(pings[0].url, "https://hc-ping.example.test/made-up-check/fail");
  // Nothing new held, but the refused one is still there.
  await run(e, server({ pings }), quietLog);
  assert.equal(pings[1].url, "https://hc-ping.example.test/made-up-check/fail");
  assert.equal(pings[1].body, "sent=0 refused=1 held=0 stuck=0");
});

test("a request held over an hour fails the check only while the server answers", async () => {
  const e = healthEnv();
  await holdRequest(e, "time-request", { request_id: ID }, Date.now() - STUCK_AFTER - 60000);
  const pings = [];
  // The server is down: /health doesn't answer, so the request is waiting, not stuck.
  let summary = await run(e, server({ health: null, request: 503, pings }), quietLog);
  assert.deepEqual(summary, { sent: 0, refused: 0, held: 1, stuck: 0 });
  assert.equal(pings[0].url, "https://hc-ping.example.test/made-up-check");
  // The server answers, but this request keeps failing to reach it.
  summary = await run(e, server({ request: 503, pings }), quietLog);
  assert.deepEqual(summary, { sent: 0, refused: 0, held: 1, stuck: 1 });
  assert.equal(pings[1].url, "https://hc-ping.example.test/made-up-check/fail");
});

test("a request held under an hour is not stuck, and the server isn't asked", async () => {
  const e = healthEnv();
  await holdRequest(e, "time-request", { request_id: ID }, Date.now() - HOUR / 2);
  let asked = false;
  const counts = await replay(e, async () => new Response("", { status: 503 }), quietLog);
  const summary = await status(e, counts, async (url) => { asked = String(url).endsWith("/health"); return new Response("ok"); });
  assert.equal(summary.stuck, 0);
  assert.equal(asked, false);
});

test("a request held before the metadata existed is timed from its stored value", async () => {
  const e = healthEnv();
  await e.OFFLINE_REQUESTS.put(`pending:time-request:${ID}`, JSON.stringify({ kind: "time-request", body: { request_id: ID }, held_at: new Date(Date.now() - 2 * HOUR).toISOString() }));
  const counts = await replay(e, async () => new Response("", { status: 503 }), quietLog);
  assert.equal((await status(e, counts, async () => new Response("ok"))).stuck, 1);
});

test("a run makes two KV list calls when nothing is held over", async () => {
  const e = healthEnv();
  await holdRequest(e, "time-request", { request_id: ID });
  await run(e, server({ pings: [] }), quietLog);
  assert.equal(e.OFFLINE_REQUESTS.lists, 2);
});

test("without the ping URL the run still happens and says it wasn't reported", async () => {
  const e = env();
  const errors = [];
  assert.equal(await report(e, { sent: 0, refused: 0, held: 0, stuck: 0 }, async () => { throw new Error("no ping expected"); }, { error: (line) => errors.push(line) }), true);
  assert.match(errors[0], /HEALTHCHECKS_OFFLINE_URL is not set/);
});
