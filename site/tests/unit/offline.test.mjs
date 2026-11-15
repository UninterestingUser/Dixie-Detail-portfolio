// The Cloudflare offline piece: signing, holding, and replaying.
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { onRequestPost } from "../../functions/offline/[kind].js";
import { deliver, replay, sign } from "../../shared/offline.js";

const KEY = "made-up-offline-signing-key-for-tests";
const ID = "0b9f1d5e-4c1a-4a6b-9f0e-2d3c4b5a6978";

function kv() {
  const store = new Map();
  return {
    store,
    async put(key, value) { store.set(key, value); },
    async get(key, type) { const value = store.get(key); return value && type === "json" ? JSON.parse(value) : value ?? null; },
    async delete(key) { store.delete(key); },
    async list({ prefix }) { return { keys: [...store.keys()].filter((k) => k.startsWith(prefix)).sort().map((name) => ({ name })), list_complete: true }; },
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
  assert.deepEqual(counts, { sent: 0, refused: 0, held: 2 });
  counts = await replay(e, async (url, options) => new Response("{}", { status: JSON.parse(options.body).request_id === ID ? 201 : 400 }), quiet);
  assert.deepEqual(counts, { sent: 1, refused: 1, held: 0 });
  assert.deepEqual([...e.OFFLINE_REQUESTS.store.keys()], [`refused:time-request:${second}`]);
});
