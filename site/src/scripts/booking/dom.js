// Small helpers for building the booking flow's markup.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "class") el.className = value;
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function field(id, label, control, hint) {
  if (hint) control.setAttribute("aria-describedby", `${id}-hint`);
  return h("div", { class: "field" }, h("label", { for: id }, label), control, hint ? h("p", { class: "hint", id: `${id}-hint` }, hint) : null);
}

// The consent wording exactly as served, with the two policy names linked.
export function consentText(words, links) {
  const parts = [];
  let rest = words;
  for (const [name, href] of [["Privacy Policy", links.privacy_policy], ["Text Message Terms", links.text_message_terms]]) {
    const at = rest.indexOf(name);
    if (at < 0 || !href) continue;
    parts.push(rest.slice(0, at), h("a", { href: new URL(href).pathname, target: "_blank", rel: "noopener" }, name));
    rest = rest.slice(at + name.length);
  }
  parts.push(rest);
  return parts;
}

// (###) ###-#### as the customer types.
export function formatPhone(text) {
  let digits = text.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) digits = digits.slice(1);
  digits = digits.slice(0, 10);
  if (!digits) return "";
  if (digits.length < 4) return `(${digits}`;
  if (digits.length < 7) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

export const phoneDigits = (text) => text.replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "");

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
