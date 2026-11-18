// Cloudflare Turnstile, run when a form is sent, and when the first photo
// is picked to open an upload session. The widget stays out of sight unless
// Cloudflare asks the visitor to tick it.
//
// A check never hangs: it fails with a TurnstileError when the site key is
// empty, the script doesn't load, the widget can't be drawn, Cloudflare
// reports an error, no token comes back, or none has come back after
// TURNSTILE_TIMEOUT (long enough for a visitor asked to tick the box).

export const TURNSTILE_TIMEOUT = 45000;

export class TurnstileError extends Error {}

let ready;
let widget;
let pending;
let script;

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
    callback: (value) => settle(null, value),
    "error-callback": () => settle(new TurnstileError("Turnstile could not check this browser.")),
    "expired-callback": () => settle(new TurnstileError("The Turnstile check expired.")),
    "timeout-callback": () => settle(new TurnstileError("The Turnstile check timed out.")),
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

function check(config, box) {
  if (!config.turnstileKey) return Promise.reject(new TurnstileError("Turnstile has no site key."));
  return load(config, box).then(
    () =>
      new Promise((resolve, reject) => {
        pending = { resolve, reject };
        try {
          window.turnstile.reset(widget);
          window.turnstile.execute(widget);
        } catch (error) {
          settle(new TurnstileError(`Turnstile could not run: ${error.message}`));
        }
      }),
  );
}

// A Turnstile token, or a TurnstileError within TURNSTILE_TIMEOUT.
export function token(config, box) {
  let timer;
  const limit = new Promise((resolve, reject) => {
    timer = setTimeout(() => {
      pending = null;
      // Not drawn yet: the next try starts over. Drawn: it reuses the widget.
      if (!widget) ready = null;
      reject(new TurnstileError("Turnstile took too long."));
    }, TURNSTILE_TIMEOUT);
  });
  return Promise.race([check(config, box), limit]).finally(() => clearTimeout(timer));
}
