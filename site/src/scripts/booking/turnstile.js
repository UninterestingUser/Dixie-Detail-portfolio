// Cloudflare Turnstile, for every form the booking page sends and for the
// quote request's photo uploads. The widget stays out of sight unless
// Cloudflare asks the visitor to tick it.
//
// The quote request card asks for a token as soon as it opens, and keeps
// one ready until it is used, getting a new one before it expires (Turnstile
// tokens last five minutes), so a first photo upload never waits on
// Turnstile (owner, 2026-11-18). Each token is used once.
//
// A check never hangs. One try fails with a TurnstileError when the script
// doesn't load, the widget can't be drawn, Cloudflare reports an error or a
// time-out, no token comes back, or none has come back after TRY_TIMEOUT
// (or INTERACTIVE_TIMEOUT once Cloudflare asks the visitor to tick the box).
// A failed try is retried on its own, up to RETRIES times RETRY_WAIT apart,
// with a freshly drawn widget, before the caller hears anything. An empty
// site key fails at once.

export const TRY_TIMEOUT = 15000;
export const INTERACTIVE_TIMEOUT = 45000;
export const RETRIES = 3;
export const RETRY_WAIT = 1500;
// Turnstile tokens are good for 300 seconds; a kept one is replaced at 240.
export const TOKEN_LIFE = 240000;

export class TurnstileError extends Error {}

let ready;
let widget;
let pending;
let script;
let inflight = null;
let kept = null;
let keptTimer = null;
let keeping = null;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function settle(error, value) {
  const waiting = pending;
  pending = null;
  if (!waiting) return;
  if (error) waiting.reject(error);
  else if (!value) waiting.reject(new TurnstileError("Turnstile gave no token."));
  else waiting.resolve(value);
}

function draw(config, box) {
  widget = window.turnstile.render(box, {
    sitekey: config.turnstileKey,
    execution: "execute",
    appearance: "interaction-only",
    "refresh-expired": "manual",
    callback: (value) => settle(null, value),
    "error-callback": () => settle(new TurnstileError("Turnstile could not check this browser.")),
    "expired-callback": () => settle(new TurnstileError("The Turnstile check expired.")),
    "timeout-callback": () => settle(new TurnstileError("The Turnstile check timed out.")),
    "before-interactive-callback": () => pending?.interactive(),
  });
}

function load(config, box) {
  if (ready) return ready;
  ready = new Promise((resolve, reject) => {
    const drawn = () => {
      try {
        draw(config, box);
        resolve();
      } catch (error) {
        reject(new TurnstileError(`Turnstile could not start: ${error.message}`));
      }
    };
    if (window.turnstile) return drawn();
    window.onTurnstileLoad = drawn;
    if (script) return;
    script = document.createElement("script");
    script.src = config.turnstileScript;
    script.async = true;
    script.onerror = () => {
      script.remove();
      script = null;
      reject(new TurnstileError("Turnstile did not load."));
    };
    document.head.append(script);
  }).catch((error) => {
    ready = null;
    widget = null;
    throw error;
  });
  return ready;
}

// After a failed try: remove the widget, so the next try draws a new one.
function discard() {
  pending = null;
  if (widget != null) {
    try {
      window.turnstile.remove(widget);
    } catch {
      // Already gone.
    }
  }
  widget = null;
  ready = null;
}

// One try: a token, or a TurnstileError within its time limit.
function attempt(config, box) {
  let timer;
  return new Promise((resolve, reject) => {
    const limit = (ms) => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        pending = null;
        reject(new TurnstileError("Turnstile took too long."));
      }, ms);
    };
    limit(TRY_TIMEOUT);
    load(config, box).then(() => {
      pending = { resolve, reject, interactive: () => limit(INTERACTIVE_TIMEOUT) };
      try {
        window.turnstile.reset(widget);
        window.turnstile.execute(widget);
      } catch (error) {
        settle(new TurnstileError(`Turnstile could not run: ${error.message}`));
      }
    }, reject);
  }).finally(() => clearTimeout(timer));
}

async function withRetries(config, box) {
  for (let tried = 0; ; tried++) {
    try {
      return await attempt(config, box);
    } catch (error) {
      discard();
      if (tried >= RETRIES) throw error instanceof TurnstileError ? error : new TurnstileError(error.message);
      await wait(RETRY_WAIT);
    }
  }
}

// One check at a time: a second caller waits on the same one. Each check
// gives a ticket, { value, taken }, so its token goes to one caller only.
function fetchToken(config, box) {
  if (!config.turnstileKey) return Promise.reject(new TurnstileError("Turnstile has no site key."));
  inflight ||= withRetries(config, box)
    .then((value) => ({ value, taken: false }))
    .finally(() => (inflight = null));
  return inflight;
}

function forget() {
  kept = null;
  clearTimeout(keptTimer);
}

// Keep a token ready while keeping is on.
function restock() {
  if (!keeping || kept || inflight) return;
  const { config, box } = keeping;
  fetchToken(config, box).then(
    (ticket) => {
      if (!keeping || ticket.taken) return;
      kept = ticket;
      clearTimeout(keptTimer);
      keptTimer = setTimeout(() => {
        kept = null;
        restock();
      }, TOKEN_LIFE);
    },
    // A failure here shows nothing: the next use tries again on its own.
    () => {},
  );
}

// Get a token now and keep one ready, as the quote request card opens.
export function keepReady(config, box) {
  if (!config.turnstileKey) return;
  keeping = { config, box };
  restock();
}

// Stop keeping a token ready, as the quote request card closes.
export function stopKeeping() {
  keeping = null;
  forget();
}

// A Turnstile token, used once, or a TurnstileError after the retries.
export async function token(config, box) {
  for (;;) {
    const ticket = kept || (await fetchToken(config, box));
    if (ticket === kept) forget();
    if (!ticket.taken) {
      ticket.taken = true;
      setTimeout(restock, 0);
      return ticket.value;
    }
  }
}
