// The address field: Google Places Autocomplete (New) through its web
// service, with the browser key, restricted to US addresses and biased to
// the service area (decision 0032). One session token covers the typing
// and the server's lookup, so the suggestions before a pick are not
// billed. Picking a suggestion hands back only its place id and the token.
// When Google fails, such as once the day's limit is used up, onDown is
// called and the form takes the address as typed.

import { h, uuid } from "./dom.js";

// Calhoun, between Cleveland and Athens: the middle of the service area.
const BIAS = { circle: { center: { latitude: 35.297, longitude: -84.749 }, radius: 50000 } };

export function addressField({ config, id, label, value = "", onPick, onDown, onType }) {
  const input = h("input", {
    id, type: "text", class: "input", value, autocomplete: "street-address", role: "combobox",
    "aria-autocomplete": "list", "aria-expanded": "false", "aria-controls": `${id}-list`, placeholder: "Start typing your street address",
  });
  const list = h("ul", { id: `${id}-list`, role: "listbox", "aria-label": "Address suggestions" });
  const box = h("div", { class: "suggestions", hidden: true }, list, h("p", { class: "by" }, "Suggestions by Google"));
  const wrapper = h("div", { class: "field" }, h("label", { for: id }, label), h("div", { class: "combo" }, input, box));
  let session = uuid();
  let items = [];
  let active = -1;
  let timer;
  let asked = 0;

  const close = () => {
    box.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  };
  const show = () => {
    list.replaceChildren(...items.map((item, index) => h("li", {
      id: `${id}-option-${index}`, role: "option", "aria-selected": index === active ? "true" : "false",
      onmousedown: (event) => { event.preventDefault(); pick(index); },
    }, h("span", {}, item.main), h("span", { class: "sub" }, item.sub))));
    if (!items.length) list.append(h("li", { role: "option", "aria-disabled": "true" }, `No matching address found. Check the spelling, or call or text ${config.phone}.`));
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `${id}-option-${active}`);
  };
  const pick = (index) => {
    const item = items[index];
    if (!item) return;
    input.value = item.text;
    close();
    const token = session;
    session = uuid();
    onPick({ placeId: item.placeId, sessionToken: token, text: item.text });
  };

  async function suggest(text) {
    const mine = ++asked;
    if (!config.mapsKey && !config.placesEndpoint.startsWith("/")) return onDown("no key");
    let response;
    try {
      response = await fetch(config.placesEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Goog-Api-Key": config.mapsKey, "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.text,suggestions.placePrediction.structuredFormat" },
        body: JSON.stringify({ input: text, sessionToken: session, includedRegionCodes: ["us"], locationBias: BIAS, includedPrimaryTypes: ["street_address", "premise", "subpremise", "route"] }),
      });
    } catch {
      return onDown("network");
    }
    if (!response.ok) return onDown(`HTTP ${response.status}`);
    const answer = await response.json().catch(() => ({}));
    if (mine !== asked) return;
    items = (answer.suggestions || []).filter((s) => s.placePrediction).slice(0, 5).map(({ placePrediction: p }) => ({
      placeId: p.placeId,
      text: p.text?.text || "",
      main: p.structuredFormat?.mainText?.text || p.text?.text || "",
      sub: p.structuredFormat?.secondaryText?.text || "",
    }));
    active = -1;
    show();
  }

  input.addEventListener("input", () => {
    onType?.(input.value);
    clearTimeout(timer);
    const text = input.value.trim();
    if (text.length < 3) return close();
    timer = setTimeout(() => suggest(text), 250);
  });
  input.addEventListener("keydown", (event) => {
    if (box.hidden) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      active = items.length ? (active + step + items.length) % items.length : -1;
      show();
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      pick(active);
    } else if (event.key === "Escape") {
      close();
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
  return { element: wrapper, input };
}
