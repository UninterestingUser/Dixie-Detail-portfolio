// Calls to the public API and to Cloudflare's offline piece. An unreachable
// server (no answer, a timeout, or a 5xx) is an OfflineError, and the flow
// switches to the forms Cloudflare holds (booking-flow.md, other cases).

export class OfflineError extends Error {}

export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.message) || `HTTP ${status}`);
    this.status = status;
    this.body = body || {};
    this.code = this.body.error;
  }
}

let config;
export function setConfig(value) {
  config = value;
}

async function call(url, options = {}, timeout = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const headers = { Accept: "application/json", ...(typeof options.body === "string" ? { "Content-Type": "application/json" } : {}) };
  let response;
  try {
    response = await fetch(url, { ...options, headers, signal: controller.signal });
  } catch (error) {
    throw new OfflineError(error.message);
  } finally {
    clearTimeout(timer);
  }
  if (response.status >= 500) throw new OfflineError(`HTTP ${response.status}`);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw new ApiError(response.status, body);
  return { status: response.status, body };
}

export function get(path, params) {
  const pairs = Object.entries(params || {}).filter(([, value]) => value != null && value !== "");
  const query = pairs.length ? "?" + new URLSearchParams(pairs).toString() : "";
  return call(`${config.api}/${path}${query}`).then((result) => result.body);
}

export function post(path, body) {
  return call(`${config.api}/${path}`, { method: "POST", body: JSON.stringify(body) });
}

export function del(path) {
  return call(`${config.api}/${path}`, { method: "DELETE" });
}

// Cloudflare's offline piece checks the Turnstile token, then holds the
// request until the server answers (functions/offline/).
export function hold(kind, body) {
  return call(`${config.offline}/${kind}`, { method: "POST", body: JSON.stringify(body) }, 20000);
}

export function apiUrl(path) {
  return `${config.api}/${path}`;
}
