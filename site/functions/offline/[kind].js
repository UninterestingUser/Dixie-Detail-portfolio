// Cloudflare Pages Function: POST /offline/time-request and
// /offline/quote-request, from the website's forms while the server can't
// be reached or Google's address suggestions are down (shared/offline.js).
//
// It checks the Turnstile token here, because a token expires long before
// a replay. Then it tries the server at once, signed: when only Google was
// down the server is up, and the request arrives right away. Otherwise it
// holds the request in Workers KV, and the scheduled Worker in
// workers/offline-replay/ replays it when the server answers.
//
// Bindings, set on the Pages project: OFFLINE_REQUESTS (KV namespace),
// API_BASE (variable), TURNSTILE_SECRET_KEY and OFFLINE_REQUESTS_SIGNING_KEY
// (secrets, from Bitwarden; docs/guides/previewing-and-deploying-the-website.md).

import { MAX_BYTES, check, deliver, holdRequest, turnstileOk } from "../../shared/offline.js";

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export async function onRequestPost({ request, env, params }) {
  const raw = await request.text();
  if (raw.length > MAX_BYTES) return json(413, { error: "too_large", message: "That form is too long. Please shorten the description." });
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    body = null;
  }
  const problem = check(params.kind, body);
  if (problem) return json(400, { error: "bad_request", message: problem });
  if (!(await turnstileOk(env, body.turnstile, request.headers.get("CF-Connecting-IP")))) {
    return json(403, { error: "turnstile_failed", message: "We couldn't confirm you're a person. Please try again." });
  }
  const { turnstile, ...form } = body;
  void turnstile;
  const outcome = await deliver(env, params.kind, form);
  if (outcome.result !== "sent") await holdRequest(env, params.kind, form);
  return json(202, { received: true });
}

export function onRequest() {
  return json(405, { error: "method_not_allowed", message: "Send the form with POST." });
}
