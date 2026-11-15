// Cloudflare Turnstile, run when a form is sent, and when the first photo
// is picked to open an upload session. The widget stays out of sight unless
// Cloudflare asks the visitor to tick it.

let ready;
let widget;
let pending;

function load(config, box) {
  if (ready) return ready;
  ready = new Promise((resolve, reject) => {
    window.onTurnstileLoad = () => {
      widget = window.turnstile.render(box, {
        sitekey: config.turnstileKey,
        execution: "execute",
        appearance: "interaction-only",
        callback: (value) => {
          pending?.resolve(value);
          pending = null;
        },
        "error-callback": () => {
          pending?.reject(new Error("Turnstile could not check this browser."));
          pending = null;
        },
      });
      resolve();
    };
    const script = document.createElement("script");
    script.src = config.turnstileScript;
    script.async = true;
    script.onerror = () => {
      ready = null;
      reject(new Error("Turnstile did not load."));
    };
    document.head.append(script);
  });
  return ready;
}

export async function token(config, box) {
  await load(config, box);
  return new Promise((resolve, reject) => {
    pending = { resolve, reject };
    try {
      window.turnstile.reset(widget);
      window.turnstile.execute(widget);
    } catch (error) {
      pending = null;
      reject(error);
    }
  });
}
