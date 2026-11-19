// The booking flow (docs/reference/booking-flow.md).
//
// Seven steps: vehicle, service and add-ons, condition (only for a service
// that covers the interior), location, date and time, details, review.
// Only steps already reached show; finishing one reveals the next and
// scrolls to it, and earlier ones can still be changed. The estimate card
// shows only the server's numbers: the latest quote, or, while the server
// can't be reached, the server's own total for the same job from the price
// table baked in at build time. Nothing here works a price out.
//
// Two other paths:
// - a quote request, for a vehicle in a class booked by quote (after the
//   vehicle step) or Full Detail or Interior Only at a level booked by
//   quote (after the condition step);
// - while the server can't be reached, or Google's address suggestions are
//   down, the form becomes a "request a time" form that Cloudflare holds and
//   replays (functions/offline/), and a quote request goes the same way,
//   without photos.

import { ApiError, OfflineError, get, hold, post, setConfig } from "./api.js";
import { consentText, field, fill, formatPhone, h, phoneDigits, uuid } from "./dom.js";
import { dollars, money } from "./money.js";
import { addressField } from "./places.js";
import { photoPicker } from "./photos.js";
import { addDays, clock, hoursText, isoDate, localDate, longDate, moment, MONTHS, monthStart } from "./time.js";
import { keepReady, stopKeeping, token, TurnstileError } from "./turnstile.js";

const root = document.querySelector("[data-booking]");
const config = JSON.parse(document.getElementById("booking-config").textContent);
const built = JSON.parse(document.getElementById("booking-built-in").textContent);
setConfig(config);

const $ = (selector) => root.querySelector(selector);
const turnstileBox = $("[data-turnstile]");
const book = built.pricebook;
const options = built.options;
const classes = new Map(book.classes.map((item) => [item.id, item]));
const services = new Map(book.services.map((item) => [item.id, item]));
const STEP_NAMES = ["", "Vehicle", "Service", "Condition", "Location", "Date", "Details", "Review"];

const fresh = () => ({
  mode: "online",
  reached: 1,
  years: null,
  makes: [],
  models: [],
  vehicle: { year: "", make: "", model: "", type: "vehicle", card: null, cardText: { year: "", make: "", model: "" }, showCards: false },
  lookup: null,
  // The size question the lookup asked (cab, third row), kept once it is
  // answered so the choices stay shown and changeable, and the answer the
  // customer gave, to it or to a photo card's sizes. The summary shows the
  // size only when there is an answer (owner, 2026-11-18).
  question: null,
  answer: null,
  size: null,
  color: "",
  service: null,
  addOns: [],
  condition: 1,
  quote: null,
  // The place token the current quote was asked for. The quote's answer
  // names no place (public-api.md), so the flow remembers what it sent.
  quotePlace: null,
  quoting: false,
  quoteError: "",
  place: null,
  placeId: null,
  sessionToken: null,
  addressText: "",
  addressError: "",
  googleDown: false,
  timesFrom: null,
  times: null,
  day: null,
  start: null,
  preferredDate: "",
  preferredTime: "",
  preferredNote: "",
  first: "",
  last: "",
  mobile: "",
  payment: null,
  appointment: false,
  request: null,
  sending: false,
  sendError: "",
  done: null,
});
let S = fresh();

// What the vehicle settled to -----------------------------------------------

function vehicleClass() {
  if (S.vehicle.card) return classes.get(S.vehicle.card) || null;
  return S.lookup && S.lookup.class ? classes.get(S.lookup.class.id) || null : null;
}

function sizes(vehicleClassValue) {
  return vehicleClassValue ? vehicleClassValue.sizes : [];
}

function sizeSettled() {
  const c = vehicleClass();
  if (!c) return false;
  if (S.vehicle.card) return c.sizes.length <= 1 || S.size != null;
  if (S.lookup.question) return false;
  return true;
}

function sizeValue() {
  const c = vehicleClass();
  if (!c) return null;
  if (S.vehicle.card) return c.sizes.length === 1 ? c.sizes[0].value : S.size;
  return S.lookup.size ? S.lookup.size.value : null;
}

function vehicleName() {
  if (S.vehicle.card) {
    const typed = [S.vehicle.cardText.year, S.vehicle.cardText.make, S.vehicle.cardText.model].filter(Boolean).join(" ");
    return typed || vehicleClass()?.name || "";
  }
  if (S.lookup) return [S.lookup.vehicle.year, S.lookup.vehicle.make, S.lookup.vehicle.model].filter(Boolean).join(" ");
  return "";
}

// The size as the customer knows it, such as "extended or crew cab". The
// vehicle class itself is internal and never shown (owner, 2026-11-18).
function sizeLine() {
  const c = vehicleClass();
  if (!c || S.answer == null) return "";
  const size = c.sizes.find((item) => item.value === sizeValue());
  return size ? size.label : "";
}

// The vehicle as the summary shows it: "2025 Chevrolet Silverado ·
// extended or crew cab (red)".
function vehicleLine() {
  const line = [vehicleName(), sizeLine()].filter(Boolean).join(" · ");
  return S.color.trim() ? `${line} (${S.color.trim()})` : line;
}

const quoteClass = () => !!vehicleClass()?.booked_by_quote;

// The vehicle as the API takes it.
function vehicleBody(forRequest = false) {
  if (S.vehicle.card) {
    const body = { photo_card: S.vehicle.card };
    if (forRequest) {
      const t = S.vehicle.cardText;
      if (/^\d{4}$/.test(t.year)) body.year = Number(t.year); // not money: a model year
      if (t.make) body.make = t.make;
      if (t.model) body.model = t.model;
    }
    return body;
  }
  return { year: Number(S.vehicle.year), make: S.vehicle.make, model: S.vehicle.model, type: S.vehicle.type }; // not money: a model year
}

const takesLevel = (id) => !!(services.get(id) && services.get(id).condition_applies);
// Whether an add-on goes with a service, from the pricebook (decision 0106).
const fits = (serviceId, addOnId) => !!(services.get(serviceId) && (services.get(serviceId).add_ons || []).includes(addOnId));
const levelFor = (number) => book.condition_levels.find((level) => level.level === number);

function cellPrice(serviceId) {
  const c = vehicleClass();
  if (!c) return null;
  const size = sizeValue();
  const prices = services.get(serviceId).prices.filter((p) => p.class_id === c.id);
  const exact = prices.find((p) => p.size === size) || prices.find((p) => p.size == null);
  return exact ? exact.price : null;
}

// The server's own total for this job, from the price table (offline).
function builtInJob() {
  const c = vehicleClass();
  if (!c || !S.service) return null;
  const addOns = [...S.addOns].sort((a, b) => a - b).join(",");
  return built.priceTable.jobs.find((job) => job.class_id === c.id && job.size === sizeValue() && job.service === S.service
    && job.condition === (takesLevel(S.service) ? S.condition : null) && job.add_ons.join(",") === addOns) || null;
}

const byQuoteLevel = () => S.service && takesLevel(S.service) && levelFor(S.condition)?.booked_by_quote;

// Steps --------------------------------------------------------------------

const conditionNeeded = () => S.service != null && takesLevel(S.service);
const stepSkipped = (n) => n === 3 && !conditionNeeded();

function stepReady(n) {
  switch (n) {
    // A vehicle booked by quote goes on to the quote request instead.
    case 1: return sizeSettled();
    case 2: return S.service != null && (S.mode === "offline" ? !!builtInJob() || byQuoteLevel() : !!S.quote || byQuoteLevel()) && !S.quoting;
    case 3: return byQuoteLevel() || (S.mode === "offline" ? !!builtInJob() : !!S.quote);
    case 4: return S.mode === "offline" ? !!(S.placeId || (S.googleDown && S.addressText.trim().length > 5)) : !!(S.place && S.quote && S.quotePlace === S.place.place && !S.quoting);
    case 5: return S.mode === "offline" ? !!S.preferredDate : !!S.start;
    case 6: return !!S.first.trim() && phoneDigits(S.mobile).length === 10 && !!S.payment;
    default: return true;
  }
}

function nextStep(n) {
  let next = n + 1;
  while (stepSkipped(next)) next++;
  return next;
}

// Going back to a step makes it current again; later steps hide until it
// is finished, keeping what they hold.
function reopen(n) {
  if (S.reached > n) S.reached = n;
}

function advance(n) {
  if (!stepReady(n)) return;
  // The one button reads "Request quote" for a job priced by hand.
  if (n === 1 && quoteClass()) return startRequest("class");
  if (n === 3 && byQuoteLevel()) return startRequest("level");
  S.reached = Math.max(S.reached, nextStep(n));
  render();
  const target = document.getElementById(`step-${S.reached}`);
  if (target) {
    target.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    target.querySelector("h2")?.focus({ preventScroll: true });
  }
}

const HINTS = {
  1: "Pick your vehicle to continue.",
  2: "Pick a service to continue.",
  3: "Pick the closest match to continue.",
  4: "Choose your address from the list to continue.",
  5: "Pick a day and an arrival time to continue.",
  6: "Add your name, a 10-digit mobile number and how you'd like to pay.",
};
const NEXT_LABEL = { 1: "Continue to services", 2: "Continue", 3: "Continue to location", 4: "Continue to date and time", 5: "Continue to your details", 6: "Continue to review" };

function frame(n, title, intro, body) {
  const done = n < S.reached;
  const current = n === S.reached;
  const section = document.getElementById(`step-${n}`);
  section.hidden = n > S.reached || stepSkipped(n);
  section.classList.toggle("current", current);
  section.classList.toggle("done-step", done);
  if (section.hidden) return section.replaceChildren();
  const ready = stepReady(n);
  const byQuote = (n === 1 && quoteClass()) || (n === 3 && byQuoteLevel());
  const label = byQuote ? "Request quote" : n === 2 ? (conditionNeeded() ? "Continue to condition" : "Continue to location") : NEXT_LABEL[n];
  const next = current && n < 7 ? h("div", { class: "next-row" },
    h("button", { type: "button", class: "button", "aria-disabled": ready ? "false" : "true", "data-continue": n, onclick: () => advance(n) }, label),
    ready ? null : h("p", { class: "hint" }, HINTS[n])) : null;
  fill(section,
    h("div", {}, h("p", { class: "step-eyebrow" }, `Step ${n} of 7${done ? " · done" : ""}`), h("h2", { id: `h-step-${n}`, tabindex: "-1" }, title), intro ? h("p", { class: "intro" }, intro) : null),
    body, next);
  return section;
}

// Step 1: the vehicle ------------------------------------------------------

function select(id, label, values, value, onchange, placeholder, disabled = false) {
  const control = h("select", { id, disabled: disabled || null, onchange: (event) => onchange(event.target.value) },
    h("option", { value: "" }, placeholder), values.map((item) => h("option", { value: item, selected: String(item) === String(value) || null }, item)));
  return field(id, label, control);
}

async function loadMakes() {
  S.makes = [];
  S.models = [];
  if (!S.vehicle.year) return render();
  try {
    S.makes = (await get("vehicles/makes", { year: S.vehicle.year })).makes;
  } catch (error) {
    return failed(error);
  }
  render();
}

async function loadModels() {
  S.models = [];
  if (!S.vehicle.make) return render();
  try {
    S.models = (await get("vehicles/models", { year: S.vehicle.year, make: S.vehicle.make })).models;
  } catch (error) {
    return failed(error);
  }
  render();
}

async function lookUp(size) {
  if (size != null) S.answer = size;
  try {
    S.lookup = await get("vehicles/lookup", { year: S.vehicle.year, make: S.vehicle.make, model: S.vehicle.model, type: S.vehicle.type, size });
  } catch (error) {
    return failed(error);
  }
  if (S.lookup.question) {
    S.question = S.lookup.question;
    S.answer = null;
  } else if (size == null) {
    S.question = null;
  }
  if (S.lookup.photo_cards) S.vehicle.showCards = true;
  vehicleChanged();
}

// A new vehicle: no lookup, question or answer yet.
function clearLookup() {
  S.lookup = null;
  S.question = null;
  S.answer = null;
}

function vehicleChanged() {
  S.service = null;
  S.addOns = [];
  S.condition = 1;
  S.quote = null;
  reopen(1);
  render();
}

function photoCards() {
  const cards = built.photoCards;
  return h("div", { class: "stack", style: "gap:12px" },
    h("p", { class: "label", style: "margin:0" }, "Pick the picture closest to your vehicle"),
    h("div", { class: "grid3" }, cards.map((card) => {
      const file = built.text.classImages[card.name];
      return h("button", {
        type: "button", class: "choice photo", "aria-pressed": S.vehicle.card === card.class_id ? "true" : "false",
        onclick: () => { S.vehicle.card = card.class_id; S.size = null; clearLookup(); vehicleChanged(); },
      }, file ? h("img", { src: `/images/vehicle-classes/${file}`, alt: "", width: "640", height: "480", loading: "lazy" }) : null,
      h("span", { class: "name" }, card.name), h("span", { class: "desc" }, card.booked_by_quote ? "Ask for a quote" : card.caption),
      card.examples.length ? h("span", { class: "desc" }, `Such as ${card.examples.join(", ")}`) : null);
    })));
}

function cardDetails() {
  const c = vehicleClass();
  const t = S.vehicle.cardText;
  const text = (key, label) => field(`card-${key}`, label, h("input", { id: `card-${key}`, class: "input", value: t[key], inputmode: key === "year" ? "numeric" : null, oninput: (event) => { t[key] = event.target.value.trim(); renderEstimate(); } }));
  return h("div", { class: "stack", style: "gap:12px" },
    h("p", { class: "hint", style: "margin:0" }, "Tell us the year, make and model if you know them (optional)."),
    h("div", { class: "grid3" }, text("year", "Year"), text("make", "Make"), text("model", "Model")),
    c && c.sizes.length > 1 ? h("div", { class: "stack", style: "gap:8px" }, h("p", { class: "label", style: "margin:0" }, "Which fits it best?"),
      h("div", { class: "grid2" }, c.sizes.map((size) => h("button", { type: "button", class: "choice", "aria-pressed": S.size === size.value ? "true" : "false", onclick: () => { S.size = size.value; S.answer = size.value; vehicleChanged(); } }, h("span", { class: "name" }, size.label[0].toUpperCase() + size.label.slice(1)))))) : null);
}

// For a vehicle booked by quote, the owner's note just above the "Request
// quote" button: text only, the first line bold.
function quoteNote() {
  const words = built.text.quoteClass;
  return h("p", { class: "quote-note", "data-quote-note": "" }, h("strong", {}, words.note_heading), h("br"), words.note);
}

function renderStep1() {
  const parts = [];
  if (S.mode === "online" && !S.vehicle.showCards) {
    parts.push(h("div", { class: "grid3" },
      select("year", "Year", S.years || [], S.vehicle.year, (value) => { S.vehicle.year = value; S.vehicle.make = ""; S.vehicle.model = ""; clearLookup(); vehicleChanged(); loadMakes(); }, S.years ? "Select year" : "Loading…"),
      select("make", "Make", S.makes, S.vehicle.make, (value) => { S.vehicle.make = value; S.vehicle.model = ""; clearLookup(); vehicleChanged(); loadModels(); }, S.vehicle.year ? "Select make" : "Pick a year first", !S.vehicle.year),
      field("model", "Model", h("select", { id: "model", disabled: !S.vehicle.make || null, onchange: (event) => {
        const model = S.models.find((m) => m.name === event.target.value);
        S.vehicle.model = model ? model.name : "";
        S.vehicle.type = model ? model.type : "vehicle";
        clearLookup();
        vehicleChanged();
        if (model) lookUp();
      } }, h("option", { value: "" }, S.vehicle.make ? "Select model" : "Pick a make first"),
      S.models.map((m) => h("option", { value: m.name, selected: m.name === S.vehicle.model || null }, m.motorcycle ? `${m.name} (Motorcycle)` : m.name))))));
    // The question stays once answered, with the answer selected.
    if (S.question) {
      parts.push(h("div", { class: "stack", style: "gap:8px", "data-size-question": "" }, h("p", { class: "label", style: "margin:0" }, S.question.text),
        h("div", { class: "grid2" }, S.question.choices.map((choice) => h("button", { type: "button", class: "choice", "aria-pressed": String(choice.answer) === String(S.answer) ? "true" : "false", onclick: () => lookUp(choice.answer) }, h("span", { class: "name" }, choice.label))))));
    }
  } else {
    if (S.lookup && S.lookup.photo_cards) parts.push(h("p", { class: "hint", style: "margin:0" }, S.lookup.message));
    parts.push(photoCards());
    if (S.vehicle.card) parts.push(cardDetails());
  }
  // The color (two thirds) and the other way to pick the vehicle (a third)
  // on one row.
  const other = S.mode !== "online" ? null : S.vehicle.showCards
    ? h("button", { type: "button", class: "link-button", onclick: () => { S.vehicle.showCards = false; S.vehicle.card = null; S.size = null; S.answer = null; vehicleChanged(); } }, "Pick the year, make and model instead")
    : h("button", { type: "button", class: "link-button", onclick: () => { S.vehicle.showCards = true; clearLookup(); vehicleChanged(); } }, "My vehicle isn't listed");
  parts.push(h("div", { class: "color-row" },
    field("color", "Color", h("input", { id: "color", class: "input", value: S.color, maxlength: "40", placeholder: "Such as silver or dark blue", oninput: (event) => (S.color = event.target.value) }),
      "Only used to tell your vehicles apart if you have two the same. It never changes the price."),
    other ? h("div", { class: "color-row-link" }, other) : null));
  if (sizeSettled() && quoteClass()) parts.push(quoteNote());
  const intro = S.mode === "offline" ? "Pick the picture closest to your vehicle. We'll confirm the details with you." : "Pick the year, make and model. We work out the vehicle's size and price it for you.";
  frame(1, "What are we detailing?", intro, h("div", { class: "stack" }, parts));
}

// Step 2: the service and add-ons -------------------------------------------

async function requote() {
  S.quote = null;
  S.quotePlace = null;
  S.quoteError = "";
  // Open times depend on the quote's time on site.
  S.times = null;
  S.timesFrom = null;
  S.start = null;
  if (S.mode === "offline" || !S.service || byQuoteLevel()) return render();
  const body = { vehicle: vehicleBody(), service: S.service, add_ons: S.addOns };
  const size = sizeValue();
  if (size != null) body.size = size;
  if (takesLevel(S.service)) body.condition = S.condition;
  if (S.place) body.place = S.place.place;
  S.quoting = true;
  render();
  try {
    S.quote = (await post("quotes", body)).body;
    S.quotePlace = body.place || null;
  } catch (error) {
    S.quoting = false;
    if (error instanceof ApiError && error.code === "ask_for_quote") return startRequest("level");
    if (error instanceof ApiError) {
      S.quoteError = error.message;
      return render();
    }
    return failed(error);
  }
  S.quoting = false;
  render();
}

// Services in the order site-content.yaml lists them; any it doesn't list
// after them.
function inOwnerOrder(list) {
  const listed = built.text.serviceOrder.map((name) => list.find((service) => service.name === name)).filter(Boolean);
  return [...listed, ...list.filter((service) => !listed.includes(service))];
}

function renderStep2() {
  const c = vehicleClass();
  if (!c) return frame(2, "Choose your service", "", h("div"));
  // In the owner's order: Full Detail, Interior Only, Exterior Only, then
  // the two paint corrections; anything not listed there after them.
  const offered = book.services.filter((service) => service.kind === "service" && cellPrice(service.id));
  const mains = inOwnerOrder(offered);
  // Only the add-ons that go with the chosen service (decision 0106), in
  // the owner's order: Carpet Extraction, Seat Extraction, Headlight
  // Restoration.
  const addOns = S.service ? inOwnerOrder(book.services.filter((service) => service.kind === "add_on" && fits(S.service, service.id) && cellPrice(service.id))) : [];
  const text = (name) => built.text.services[name] || {};
  const body = h("div", { class: "stack" },
    h("div", { class: "choices" }, mains.map((service) => h("button", {
      type: "button", class: "choice", "aria-pressed": S.service === service.id ? "true" : "false", "data-service": service.name,
      onclick: () => { S.service = service.id; S.condition = 1; S.addOns = S.addOns.filter((id) => fits(service.id, id)); reopen(2); requote(); },
    }, h("span", { class: "top" }, h("span", { class: "name" }, service.name), h("span", { class: "price" }, dollars(cellPrice(service.id)))),
    h("span", { class: "desc" }, text(service.name).card || service.description)))),
    addOns.length ? h("div", { class: "stack", style: "gap:10px" }, h("h3", { style: "margin:0;font-size:19px" }, "Available add-ons"),
      addOns.map((service) => h("label", { class: "tick" },
        h("input", { type: "checkbox", checked: S.addOns.includes(service.id) || null, "data-add-on": service.name, onchange: (event) => {
          S.addOns = event.target.checked ? [...S.addOns, service.id] : S.addOns.filter((id) => id !== service.id);
          reopen(2);
          requote();
        } }),
        h("span", { class: "body" }, h("span", { class: "top", style: "display:flex;justify-content:space-between;gap:12px" }, h("strong", {}, service.name), h("strong", { class: "add-on-price" }, `+ ${dollars(cellPrice(service.id))}`)),
          h("span", { class: "desc", style: "font-size:15px;color:var(--text)" }, text(service.name).card || service.description))))) : null,
    S.quoteError ? h("p", { class: "error", role: "alert" }, S.quoteError) : null);
  const intro = `Prices for your ${vehicleName() || c.name}, before any condition adjustment.`;
  frame(2, "Choose your service", intro, body);
}

// Step 3: the condition (service level) -------------------------------------

function renderStep3() {
  const levels = book.condition_levels;
  const body = h("div", { class: "stack" },
    h("div", { class: "choices" }, levels.map((level) => {
      const words = built.text.levels[level.level] || {};
      const change = level.booked_by_quote ? "Ask for a quote" : level.adds_percent === "0" ? "No change" : `+${level.adds_percent}%`;
      return h("button", {
        type: "button", class: "choice", "aria-pressed": S.condition === level.level ? "true" : "false", "data-level": level.level,
        onclick: () => { S.condition = level.level; reopen(3); requote(); },
      }, h("span", { class: "top" }, h("span", { class: "name" }, words.name || `Service Level ${level.level}`), h("span", { class: "price" }, change)),
      h("span", { class: "desc" }, words.card || level.description));
    })),
    byQuoteLevel() ? h("p", { class: "quote-note", "data-quote-note": "" }, (built.text.levels[S.condition] || {}).quoteNote) : null);
  frame(3, "What is the condition of the interior?", "Pick the one closest to today. We confirm it when we arrive.", body);
}

// Step 4: the location ------------------------------------------------------

async function placePicked({ placeId, sessionToken, text }) {
  S.addressText = text;
  S.addressError = "";
  // Kept for an offline request, which sends the place id itself.
  S.placeId = placeId;
  S.sessionToken = sessionToken;
  if (S.mode === "offline") return render();
  try {
    S.place = (await post("addresses", { place_id: placeId, session_token: sessionToken })).body;
  } catch (error) {
    S.place = null;
    if (error instanceof ApiError) {
      S.addressError = error.message;
      return render();
    }
    return failed(error);
  }
  await requote();
}

function googleDown() {
  if (S.googleDown) return;
  S.googleDown = true;
  S.place = null;
  goOffline("Address suggestions aren't working just now, so type your address and we'll confirm your booking by text or call.");
}

function renderStep4() {
  const typed = S.googleDown;
  const parts = [];
  if (typed) {
    parts.push(field("address-typed", "Service address", h("input", { id: "address-typed", class: "input", value: S.addressText, autocomplete: "street-address", oninput: (event) => { S.addressText = event.target.value; refreshContinue(4); } }),
      "Street, city and ZIP code. We'll check it before we confirm."));
  } else {
    parts.push(addressField({ config, id: "address", label: "Service address", value: S.addressText, onPick: placePicked, onDown: googleDown, onType: (value) => { S.addressText = value; S.place = null; S.placeId = null; reopen(4); refreshContinue(4); } }).element);
  }
  // In the area: just that, since the estimate card shows the tax. Outside
  // it: only the server's "Sorry..." message.
  if (S.place) parts.push(h("div", { class: "banner", "data-in-area": "" }, h("strong", {}, "In our service area")));
  if (S.addressError) parts.push(h("div", { class: "banner warn", role: "alert" }, h("div", {}, S.addressError)));
  parts.push(h("p", { class: "hint", style: "margin:0" }, h("strong", {}, "What we need from you: "), "room to work, plus water and power within 50 feet. We bring everything else, tent included."));
  frame(4, "Where will the vehicle be?", "Home, work or anywhere convenient in Bradley, McMinn, Hamilton, Polk or Meigs County.", h("div", { class: "stack" }, parts));
}

// Step 5: the date and arrival time -----------------------------------------

async function loadTimes(from) {
  S.times = null;
  S.timesFrom = from || "first";
  render();
  try {
    S.times = await get("open-times", { quote: S.quote.number, from, days: 31 });
  } catch (error) {
    return failed(error);
  }
  render();
}

function renderCalendar() {
  if (!S.times) return h("p", { class: "loading" }, "Finding open days…");
  const open = new Map(S.times.days.map((day) => [day.date, day.times]));
  const first = monthStart(localDate(S.times.from));
  const cells = [];
  for (let i = 0; i < first.getDay(); i++) cells.push(h("span"));
  for (let day = first; day.getMonth() === first.getMonth(); day = addDays(day, 1)) {
    const date = isoDate(day);
    const label = `${MONTHS[day.getMonth()]} ${day.getDate()}`;
    if (open.has(date)) cells.push(h("button", { type: "button", "aria-pressed": S.day === date ? "true" : "false", "aria-label": `${label}, open`, "data-day": date, onclick: () => { S.day = date; S.start = null; reopen(5); render(); } }, String(day.getDate())));
    else cells.push(h("span", { class: "day", "aria-label": `${label}, not open` }, String(day.getDate())));
  }
  const today = monthStart(new Date());
  return h("div", { class: "stack", style: "gap:10px" },
    h("div", { class: "month-bar" },
      h("button", { type: "button", class: "link-button", disabled: first <= today || null, onclick: () => loadTimes(isoDate(monthStart(first, -1))) }, "← Earlier"),
      h("strong", {}, `${MONTHS[first.getMonth()]} ${first.getFullYear()}`),
      h("button", { type: "button", class: "link-button", onclick: () => loadTimes(isoDate(monthStart(first, 1))) }, "Later →")),
    h("div", { class: "calendar", role: "group", "aria-label": "Open days" }, ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => h("span", { class: "dow", "aria-hidden": "true" }, d)), cells),
    S.day ? h("div", { class: "stack", style: "gap:8px" }, h("p", { class: "label", style: "margin:0" }, `Arrival time, ${longDate(S.day)}`),
      h("div", { class: "times" }, (open.get(S.day) || []).map((slot) => h("button", { type: "button", class: "choice", "aria-pressed": S.start === slot.start ? "true" : "false", "data-time": slot.label, onclick: () => { S.start = slot.start; reopen(5); render(); } }, slot.label)))) : null);
}

function renderOfflineDate() {
  const today = new Date();
  const min = isoDate(addDays(today, built.minimumNoticeDays));
  const max = isoDate(addDays(today, built.furthestDays));
  const weekday = S.preferredDate ? ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][localDate(S.preferredDate).getDay()] : null;
  const times = (weekday && built.startTimes[weekday]) || [];
  return h("div", { class: "stack" },
    h("div", { class: "grid2" },
      field("pref-date", "Preferred day", h("input", { id: "pref-date", type: "date", class: "input", min, max, value: S.preferredDate, onchange: (event) => { S.preferredDate = event.target.value; S.preferredTime = ""; reopen(5); render(); } })),
      field("pref-time", "Preferred arrival", h("select", { id: "pref-time", disabled: !times.length || null, onchange: (event) => (S.preferredTime = event.target.value) }, h("option", { value: "" }, weekday && !times.length ? "Closed that day" : "Any time"), times.map((t) => h("option", { value: t, selected: t === S.preferredTime || null }, clock(t)))))),
    field("pref-note", "Anything about timing (optional)", h("textarea", { id: "pref-note", maxlength: "300", oninput: (event) => (S.preferredNote = event.target.value) }, S.preferredNote)));
}

function renderStep5() {
  if (S.mode === "online" && S.reached >= 5 && S.quote && !S.times && S.timesFrom == null) queueMicrotask(() => loadTimes(null));
  const offline = S.mode === "offline";
  frame(5, offline ? "When would you like us?" : "Pick a day and arrival time",
    offline ? "We'll confirm the day and time by text or call." : "One vehicle per day, so your detail gets the whole day.",
    offline ? renderOfflineDate() : renderCalendar());
}

// Step 6: the details --------------------------------------------------------

function renderStep6() {
  const mobile = h("input", { id: "mobile", type: "tel", class: "input", inputmode: "tel", autocomplete: "tel-national", placeholder: "(###) ###-####", maxlength: "14", value: S.mobile, oninput: (event) => {
    event.target.value = formatPhone(event.target.value);
    S.mobile = event.target.value;
    refreshContinue(6);
  } });
  const body = h("div", { class: "stack" },
    h("div", { class: "grid2" },
      field("first", "First name", h("input", { id: "first", class: "input", autocomplete: "given-name", value: S.first, maxlength: "100", oninput: (event) => { S.first = event.target.value; refreshContinue(6); } })),
      field("last", "Last name", h("input", { id: "last", class: "input", autocomplete: "family-name", value: S.last, maxlength: "100", oninput: (event) => (S.last = event.target.value) }))),
    field("mobile", "Mobile number", mobile),
    h("div", { class: "stack", style: "gap:8px" }, h("p", { class: "label", style: "margin:0" }, "How would you like to pay when we're done?"),
      h("div", { class: "times", role: "group", "aria-label": "Payment method" }, options.payment_methods.map((method) => h("button", { type: "button", class: "choice", "aria-pressed": S.payment === method.value ? "true" : "false", onclick: () => { S.payment = method.value; refreshContinue(6); renderStep6(); } }, method.label))),
      h("p", { class: "hint", style: "margin:0" }, "Nothing is charged now. Payment is due when the work is finished.")));
  frame(6, "Your details", "", body);
}

// One unchecked checkbox, not required (decision 0108).
function consentBoxes(consent) {
  return h("div", { class: "stack", style: "gap:10px" },
    h("label", { class: "tick" }, h("input", { type: "checkbox", id: "consent-appointment", checked: S.appointment || null, onchange: (event) => (S.appointment = event.target.checked) }),
      h("span", { class: "consent" }, consentText(consent.appointment, consent.links))));
}

// Step 7: review and book ----------------------------------------------------

function reviewRows() {
  const job = S.mode === "online" ? S.quote : null;
  const service = services.get(S.service);
  const rows = [
    ["Vehicle", vehicleLine()],
    ["Service", [service ? service.name : "", ...S.addOns.map((id) => services.get(id).name)].join(" + ")],
  ];
  if (takesLevel(S.service)) rows.push(["Condition", (built.text.levels[S.condition] || {}).name || `Level ${S.condition}`]);
  rows.push(["Address", job && job.address ? job.address : S.addressText]);
  if (S.mode === "online" && S.start && S.day) rows.push(["Arrival", `${longDate(S.day)} at ${(S.times?.days.find((d) => d.date === S.day)?.times.find((t) => t.start === S.start) || {}).label || ""}`]);
  if (S.mode === "offline") rows.push(["Preferred", S.preferredDate ? `${longDate(S.preferredDate)}${S.preferredTime ? ` at ${clock(S.preferredTime)}` : ""}` : ""]);
  rows.push(["Name", `${S.first} ${S.last}`.trim()], ["Mobile", S.mobile], ["Payment", (options.payment_methods.find((m) => m.value === S.payment) || {}).label || ""]);
  return rows;
}

function renderStep7() {
  const offline = S.mode === "offline";
  const total = offline ? builtInJob()?.total_before_tax : S.quote?.total;
  const body = h("div", { class: "stack" },
    h("dl", { class: "review-list" }, reviewRows().map(([key, value]) => h("div", {}, h("dt", {}, key), h("dd", {}, value)))),
    h("div", { class: "next-row", style: "justify-content:space-between" },
      h("span", {}, offline ? "Estimated total before sales tax" : S.quote?.sales_tax ? "Estimated total with sales tax" : "Estimated total before sales tax"),
      h("strong", { style: "font-size:28px;color:var(--navy)", "data-review-total": "" }, money(total))),
    S.sendError ? h("p", { class: "error", role: "alert" }, S.sendError) : null,
    consentBoxes(options.consent),
    h("button", { type: "button", class: "button", "aria-disabled": S.sending ? "true" : null, "data-book": "", onclick: () => (offline ? sendTimeRequest() : sendBooking()) },
      S.sending ? "Sending…" : offline ? "Send my request" : "Book my appointment"),
    h("p", { class: "hint", style: "margin:0" }, offline
      ? "We'll confirm your day and the final price by text or call. Nothing is charged until the job is done."
      : "Nothing is charged now. We confirm the final price when we see the vehicle, and you pay when the job is done."));
  frame(7, offline ? "Review and send" : "Review and book", "", body);
}

// Why a send failed, in plain words with the phone number. Every send gives
// up in a set time (api.js, turnstile.js) and the button comes back; the
// form keeps everything the customer entered, so trying again is one click.
function sendFailed(error) {
  if (error instanceof ApiError) {
    return error.message.includes(config.phone) ? error.message : `${error.message} Questions? Call or text ${config.phone}.`;
  }
  const what = error instanceof TurnstileError ? "We couldn't check this browser just now, so nothing was sent." : "We couldn't send that just now.";
  return `${what} Everything you entered is still here. Please try again, or call or text ${config.phone}.`;
}

async function sendBooking() {
  if (S.sending) return;
  S.sending = true;
  S.sendError = "";
  render();
  let answer;
  try {
    const value = await token(config, turnstileBox);
    answer = await post("bookings", {
      quote: S.quote.number, start: S.start, first_name: S.first.trim(), last_name: S.last.trim() || undefined, mobile: S.mobile,
      payment_method: S.payment, color: S.color.trim() || undefined, consents: { version: options.consent.version, appointment: S.appointment }, turnstile: value,
    });
  } catch (error) {
    S.sending = false;
    if (error instanceof ApiError) return bookingRefused(error);
    if (error instanceof OfflineError) return failed(error);
    S.sendError = sendFailed(error);
    return render();
  }
  S.sending = false;
  S.done = { kind: answer.status === 202 ? "second" : "booked", answer: answer.body };
  render();
}

function bookingRefused(error) {
  if ((error.code === "quote_expired" || error.code === "quote_changed") && error.body.quote) {
    S.quote = error.body.quote;
    S.sendError = `${error.message} The estimate now shows it.`;
  } else if (error.code === "time_taken") {
    S.start = null;
    S.times = null;
    S.timesFrom = null;
    S.reached = 5;
    showBanner(error.message, true);
  } else if (error.code === "ask_for_quote") {
    return startRequest("level");
  } else {
    S.sendError = sendFailed(error);
  }
  render();
}

function offlineBody() {
  const job = builtInJob();
  const body = {
    request_id: S.requestId ||= uuid(),
    submitted_at: new Date().toISOString(),
    vehicle: vehicleBody(true),
    service: S.service,
    add_ons: S.addOns,
    first_name: S.first.trim(),
    mobile: S.mobile,
    payment_method: S.payment,
    consents: { version: options.consent.version, appointment: S.appointment },
    shown: { total: job.total_before_tax, pricebook_version: built.priceTable.pricebook_version },
  };
  const size = sizeValue();
  if (size != null) body.size = size;
  if (takesLevel(S.service)) body.condition = S.condition;
  if (S.placeId) {
    body.place_id = S.placeId;
    body.session_token = S.sessionToken;
  } else body.address = S.addressText.trim();
  if (S.preferredDate) body.preferred_start = moment(S.preferredDate, S.preferredTime || "08:00");
  if (S.preferredNote.trim() || (S.preferredDate && !S.preferredTime)) body.preferred_note = [S.preferredNote.trim(), S.preferredDate && !S.preferredTime ? "Any arrival time" : ""].filter(Boolean).join(". ");
  if (S.last.trim()) body.last_name = S.last.trim();
  if (S.color.trim()) body.color = S.color.trim();
  return body;
}

async function sendTimeRequest() {
  if (S.sending) return;
  S.sending = true;
  S.sendError = "";
  render();
  try {
    const value = await token(config, turnstileBox);
    await hold("time-request", { ...offlineBody(), turnstile: value });
  } catch (error) {
    S.sending = false;
    S.sendError = sendFailed(error);
    return render();
  }
  S.sending = false;
  S.done = { kind: "held" };
  render();
}

// The quote request ----------------------------------------------------------

let picker = null;

function startRequest(reason) {
  S.request = {
    reason,
    service: reason === "level" ? S.service : S.service || "not_sure",
    condition: reason === "level" ? S.condition : null,
    addOns: [...S.addOns],
    description: "",
    days: "",
  };
  picker = null;
  render();
  $("[data-request]").scrollIntoView({ block: "start" });
  document.getElementById("h-request")?.focus({ preventScroll: true });
}

// Whether a service is for a vehicle class (site-content.yaml, only_for):
// Motorcycle Detail only for motorcycles, the others never for them, so a
// van's quote request never offers Motorcycle Detail (owner, 2026-11-18).
function forClass(service, c) {
  if (!c) return true;
  const only = (name) => (built.text.services[name] || {}).onlyFor || [];
  const special = Object.keys(built.text.services).some((name) => only(name).includes(c.name));
  return special ? only(service.name).includes(c.name) : only(service.name).length === 0;
}

function renderRequest() {
  const section = $("[data-request]");
  section.hidden = !S.request || !!S.done;
  // A Turnstile token is fetched as soon as the card opens and kept fresh
  // while it is open (turnstile.js), so photos upload at once.
  if (section.hidden || S.mode === "offline") stopKeeping();
  if (section.hidden) return;
  const r = S.request;
  const offline = S.mode === "offline";
  if (!offline) keepReady(config, turnstileBox);
  const c = vehicleClass();
  const why = r.reason === "class"
    ? built.text.quoteClass.request_intro.replace("{class}", c ? c.name : "These vehicles")
    : (built.text.levels[r.condition] || {}).requestIntro || "We'll reply with a price, usually within a day.";
  const mains = book.services.filter((service) => service.kind === "service" && forClass(service, c) && (!c || c.booked_by_quote || service.prices.some((p) => p.class_id === c.id)));
  if (!offline && !picker) picker = photoPicker({ config, limits: options.photos, box: turnstileBox });
  const serviceControl = h("select", { id: "qr-service", onchange: (event) => {
    r.service = event.target.value === "not_sure" ? "not_sure" : Number(event.target.value); // not money: a service id
    if (r.service === "not_sure" || !takesLevel(r.service)) r.condition = null;
    r.addOns = r.addOns.filter((id) => fits(r.service, id));
    renderRequest();
  } }, h("option", { value: "not_sure", selected: r.service === "not_sure" || null }, "Not sure"),
  mains.map((service) => h("option", { value: service.id, selected: r.service === service.id || null }, service.name)));
  const address = S.googleDown || (offline && !config.mapsKey && !config.placesEndpoint.startsWith("/"))
    ? field("qr-address", "Service address", h("input", { id: "qr-address", class: "input", value: S.addressText, oninput: (event) => { S.addressText = event.target.value; } }), "Street, city and ZIP code.")
    : addressField({ config, id: "qr-address", label: "Service address", value: S.place ? S.place.address.one_line : S.addressText, onPick: placePicked, onDown: () => { S.googleDown = true; renderRequest(); }, onType: (value) => { S.addressText = value; S.place = null; S.placeId = null; } }).element;
  const level = r.condition ? levelFor(r.condition) : null;
  fill(section,
    h("div", {}, h("p", { class: "step-eyebrow" }, "Ask for a quote"), h("h2", { id: "h-request", tabindex: "-1" }, "Tell us about the job"), h("p", { class: "intro" }, why)),
    h("dl", { class: "review-list" },
      h("div", {}, h("dt", {}, "Vehicle"), h("dd", {}, vehicleLine() || "Not given")),
      level ? h("div", {}, h("dt", {}, "Condition"), h("dd", {}, (built.text.levels[level.level] || {}).name || `Level ${level.level}`)) : null,
      r.addOns.length ? h("div", {}, h("dt", {}, "Add-ons"), h("dd", {}, r.addOns.map((id) => services.get(id).name).join(", "))) : null),
    field("qr-service", "The service you want", serviceControl),
    // The owner's guidance sits under the heading, above the field.
    h("div", { class: "field" }, h("label", { for: "qr-description" }, "What do you need?"),
      h("p", { class: "hint", id: "qr-description-hint" }, "Provide relevant details about the vehicle (size, interior configuration, etc.) and what you need done."),
      h("textarea", { id: "qr-description", required: true, maxlength: "2000", "aria-describedby": "qr-description-hint", oninput: (event) => (r.description = event.target.value) }, r.description)),
    offline ? h("p", { class: "notice" }, `Photos can't be sent just now. Send the request, then text photos to ${config.phone} if you'd like.`) : picker.element,
    address,
    h("div", { class: "grid2" },
      field("qr-first", "First name", h("input", { id: "qr-first", class: "input", autocomplete: "given-name", value: S.first, oninput: (event) => (S.first = event.target.value) })),
      field("qr-last", "Last name", h("input", { id: "qr-last", class: "input", autocomplete: "family-name", value: S.last, oninput: (event) => (S.last = event.target.value) }))),
    field("qr-mobile", "Mobile number", h("input", { id: "qr-mobile", type: "tel", class: "input", inputmode: "tel", autocomplete: "tel-national", placeholder: "(###) ###-####", maxlength: "14", value: S.mobile, oninput: (event) => { event.target.value = formatPhone(event.target.value); S.mobile = event.target.value; } })),
    field("qr-days", "Preferred days (optional)", h("input", { id: "qr-days", class: "input", maxlength: "300", value: r.days, placeholder: "Such as weekdays, a specific date, etc.", oninput: (event) => (r.days = event.target.value) })),
    S.sendError ? h("p", { class: "error", role: "alert" }, S.sendError) : null,
    consentBoxes(options.consent),
    h("div", { class: "next-row" },
      h("button", { type: "button", class: "button", "data-send-request": "", onclick: sendRequest }, S.sending ? "Sending…" : "Send my request"),
      h("button", { type: "button", class: "link-button", onclick: () => { S.request = null; S.sendError = ""; render(); } }, "Back to booking")));
}

function requestProblem() {
  const r = S.request;
  if (!r.description.trim()) return "Tell us what you need.";
  if (S.mode === "online" && !S.googleDown && !S.place) return "Choose your address from the list.";
  if ((S.mode === "offline" || S.googleDown) && !S.placeId && S.addressText.trim().length < 6 && !S.place) return "Enter your address.";
  if (!S.first.trim()) return "Add your first name.";
  if (phoneDigits(S.mobile).length !== 10) return "Add a 10-digit mobile number.";
  return "";
}

async function sendRequest() {
  if (S.sending) return;
  S.sendError = requestProblem();
  if (S.sendError) return renderRequest();
  const r = S.request;
  const base = {
    vehicle: vehicleBody(true),
    service: r.service,
    description: r.description.trim(),
    first_name: S.first.trim(),
    mobile: S.mobile,
    consents: { version: options.consent.version, appointment: S.appointment },
  };
  if (S.last.trim()) base.last_name = S.last.trim();
  if (r.days.trim()) base.preferred_days = r.days.trim();
  const size = sizeValue();
  if (size != null && !S.vehicle.card) base.size = size;
  if (r.condition && r.service !== "not_sure" && takesLevel(r.service)) base.condition = r.condition;
  if (r.addOns.length && r.service !== "not_sure") base.add_ons = r.addOns;
  S.sending = true;
  renderRequest();
  const offline = S.mode === "offline" || S.googleDown;
  try {
    if (offline) {
      const value = await token(config, turnstileBox);
      const body = { ...base, request_id: S.requestId ||= uuid(), submitted_at: new Date().toISOString(), turnstile: value };
      if (size != null && S.vehicle.card) body.size = size;
      if (S.placeId) { body.place_id = S.placeId; body.session_token = S.sessionToken; } else body.address = S.addressText.trim();
      await hold("quote-request", body);
      S.done = { kind: "request-held" };
    } else {
      const { session, photos } = await picker.ready();
      const value = await token(config, turnstileBox);
      const body = { ...base, place: S.place.place, turnstile: value };
      if (session) { body.session = session; body.photos = photos; }
      const answer = await post("quote-requests", body);
      S.done = { kind: "request", answer: answer.body };
    }
  } catch (error) {
    S.sending = false;
    if (error instanceof OfflineError && !offline) {
      goOffline("We can't reach our booking system just now. Your request can still be sent, without photos.");
      return;
    }
    S.sendError = sendFailed(error);
    return renderRequest();
  }
  S.sending = false;
  render();
}

// Done ---------------------------------------------------------------------

function renderDone() {
  const section = $("[data-done]");
  section.hidden = !S.done;
  if (!S.done) return;
  const d = S.done;
  let body;
  if (d.kind === "booked") {
    const s = d.answer.summary;
    const file = d.answer.calendar_file;
    const href = `data:${file.content_type};charset=utf-8,${encodeURIComponent(file.content)}`;
    body = [
      h("h2", { id: "h-done", tabindex: "-1" }, "You're booked"),
      h("p", { class: "lead" }, `Your booking reference is ${d.answer.reference}. ${S.appointment ? "We'll text you a confirmation." : ""}`),
      h("dl", { class: "review-list" }, [["Service", [s.service, ...s.add_ons].join(", ")], ["Vehicle", s.vehicle], ["Arrival", s.arrival], ["Time on site", s.time_on_site], ["Address", s.address], ["Total before tax", money(s.total_before_tax)], ["Sales tax", money(s.sales_tax)], ["Estimated total", money(s.total)], ["Payment", s.payment_method]].map(([k, v]) => h("div", {}, h("dt", {}, k), h("dd", {}, v)))),
      h("div", { class: "buttons" }, h("a", { class: "button", href, download: file.name, "data-calendar-file": "" }, "Add to my calendar")),
      h("ul", {}, s.notes.map((note) => h("li", {}, note))),
    ];
  } else if (d.kind === "second") {
    body = [h("h2", { id: "h-done", tabindex: "-1" }, "Request received"), h("p", { class: "lead" }, d.answer.message)];
  } else if (d.kind === "request") {
    body = [h("h2", { id: "h-done", tabindex: "-1" }, "Request sent"), h("p", { class: "lead" }, d.answer.message)];
  } else if (d.kind === "request-held") {
    body = [h("h2", { id: "h-done", tabindex: "-1" }, "Request sent"), h("p", { class: "lead" }, `Thanks! We've got your request and will reply with a price, usually within a day. If you have photos, text them to ${config.phone}.`)];
  } else {
    body = [h("h2", { id: "h-done", tabindex: "-1" }, "Request sent"), h("p", { class: "lead" }, `Thanks! We've got your request and will confirm your day and price by text or call. Questions? Call or text ${config.phone}.`)];
  }
  fill(section, body);
  $("[data-flow]").hidden = true;
  section.focus();
}

// The estimate card ----------------------------------------------------------

// The estimate card's condition line in the owner's words, such as "Needs
// Attention (+10%)", the percentage from the price book.
function conditionLine(number) {
  const level = levelFor(number);
  const label = (built.text.levels[number] || {}).estimate || `Level ${number}`;
  return level && level.adds_percent ? `${label} (+${level.adds_percent}%)` : label;
}

function estimateContent() {
  const parts = [h("p", { class: "eyebrow-light" }, "Your estimate")];
  const name = vehicleName();
  parts.push(h("div", {}, h("p", { class: "vehicle" }, name || "Your vehicle"), name || vehicleClass() ? null : h("p", { class: "sub" }, "Pick your vehicle to start.")), h("hr"));
  let total = null;
  let note = "";
  let hours = "";
  if (S.request || byQuoteLevel() || vehicleClass()?.booked_by_quote) {
    parts.push(h("p", { class: "sub" }, "Ask for a quote: this job is priced by hand, and we'll reply with a price."));
    note = "Quoted by hand";
  } else if (S.mode === "offline" && S.service) {
    const job = builtInJob();
    if (job) {
      parts.push(h("div", { class: "lines" }, [S.service, ...S.addOns].map((id) => h("div", { class: "line" }, h("span", {}, services.get(id).name))),
        takesLevel(S.service) && S.condition > 1 ? h("div", { class: "line" }, h("span", {}, conditionLine(S.condition))) : null), h("hr"));
      parts.push(h("p", { class: "sub" }, `Sales tax is added for your address. Prices from our price list, version ${built.priceTable.pricebook_version}.`));
      total = job.total_before_tax;
      note = "before sales tax";
      hours = hoursText(job.time_on_site_minutes, job.full_day);
    }
  } else if (S.quote) {
    const q = S.quote;
    parts.push(h("div", { class: "lines" }, q.lines.map((line) => h("div", { class: "line" }, h("span", {}, line.kind === "condition" ? conditionLine(q.condition_level) : line.description), h("span", {}, money(line.amount))))), h("hr"));
    parts.push(h("div", { class: "line" }, h("span", {}, "Subtotal"), h("span", {}, money(q.total_before_tax))));
    if (q.sales_tax) parts.push(h("div", { class: "line" }, h("span", {}, `Sales tax (${q.sales_tax.rate_percent}%)`), h("span", {}, money(q.sales_tax.amount))));
    else parts.push(h("p", { class: "sub" }, "Sales tax is added once we have your address."));
    total = q.sales_tax ? q.total : q.total_before_tax;
    note = q.sales_tax ? "with sales tax" : "before sales tax";
    hours = hoursText(q.time_on_site_minutes, q.full_day);
  } else if (S.quoting) {
    parts.push(h("p", { class: "sub" }, "Pricing…"));
  } else {
    parts.push(h("p", { class: "sub" }, vehicleClass() ? "Pick a service to see your price." : "Your price builds here as you go."));
  }
  if (total) {
    parts.push(h("div", { class: "total" }, h("span", { class: "sub" }, "Estimated total", h("br"), note), h("span", { class: "amount", "data-total": "" }, money(total))));
    if (hours) parts.push(h("p", { class: "time" }, hours));
  }
  parts.push(h("p", { class: "fine" }, "The final price is confirmed when we see the vehicle. Nothing is charged until the job is done."));
  return { parts, total, note, hours };
}

function renderEstimate() {
  const { parts, total, note, hours } = estimateContent();
  fill($("[data-estimate]"), parts);
  const sheet = $("[data-sheet-body]");
  fill(sheet, h("div", { class: "estimate" }, ...estimateContent().parts));
  const bar = $("[data-phone-bar]");
  bar.hidden = !!S.done;
  $("[data-bar-total]").textContent = total ? money(total) : "—";
  $("[data-bar-note]").textContent = [total ? note : "Pick your vehicle", hours].filter(Boolean).join(" · ");
}

// Banners, offline -----------------------------------------------------------

function showBanner(text, warn = false) {
  const el = $("[data-banner]");
  el.textContent = text;
  el.hidden = !text;
  el.classList.toggle("warn", warn);
}

function goOffline(message) {
  if (S.mode !== "offline") {
    S.mode = "offline";
    S.quote = null;
    S.place = null;
    if (S.lookup && !S.vehicle.card && S.lookup.class) {
      // Keep the vehicle the server settled, as a photo card with its name.
      S.vehicle.card = S.lookup.class.id;
      S.vehicle.cardText = { year: String(S.lookup.vehicle.year || ""), make: S.lookup.vehicle.make || "", model: S.lookup.vehicle.model || "" };
      S.size = S.lookup.size ? S.lookup.size.value : null;
    }
    S.vehicle.showCards = true;
    if (!sizeSettled()) S.reached = 1;
    else if (S.reached > 4) S.reached = 4;
  }
  showBanner(message || `We can't reach our booking system just now. You can still send a request with the prices below, and we'll confirm by text or call. Questions? Call or text ${config.phone}.`, true);
  render();
}

function failed(error) {
  if (error instanceof OfflineError) return goOffline();
  showBanner(error.message || "Something went wrong. Please try again.", true);
  render();
}

function refreshContinue(n) {
  const button = root.querySelector(`[data-continue="${n}"]`);
  if (!button) return;
  const ready = stepReady(n);
  button.setAttribute("aria-disabled", ready ? "false" : "true");
  const hint = button.nextElementSibling;
  if (hint) hint.hidden = ready;
}

// Progress, render -----------------------------------------------------------

function renderProgress() {
  for (const pill of root.querySelectorAll("[data-pill]")) {
    const n = Number(pill.dataset.pill); // not money: a step number
    const skipped = stepSkipped(n) && S.reached > 2;
    const done = S.done || n < S.reached;
    pill.classList.toggle("done", !!done && !skipped);
    pill.classList.toggle("current", !S.done && !S.request && n === S.reached);
    pill.classList.toggle("skipped", skipped);
    pill.querySelector(".state").textContent = skipped ? ", not needed" : done ? ", done" : n === S.reached ? ", current step" : "";
    if (n === S.reached) pill.setAttribute("aria-current", "step");
    else pill.removeAttribute("aria-current");
  }
}

function render() {
  const active = document.activeElement && document.activeElement.id;
  const caret = active && document.activeElement.selectionStart;
  document.getElementById("step-1").style.minHeight = "";
  $("[data-flow]").hidden = !!S.done || !!S.request;
  renderStep1();
  renderStep2();
  renderStep3();
  renderStep4();
  renderStep5();
  renderStep6();
  renderStep7();
  renderRequest();
  renderDone();
  renderProgress();
  renderEstimate();
  if (active && !S.done) {
    const el = document.getElementById(active);
    if (el && el !== document.activeElement) {
      el.focus({ preventScroll: true });
      if (typeof caret === "number" && el.setSelectionRange) try { el.setSelectionRange(caret, caret); } catch { /* not a text field */ }
    }
  }
}

// Phone bar, sheet, start over -------------------------------------------------

const sheetDialog = $("[data-sheet]");
$("[data-open-estimate]").addEventListener("click", () => sheetDialog.showModal());
$("[data-close-sheet]").addEventListener("click", () => sheetDialog.close());
const goCurrent = (event) => {
  event.preventDefault();
  sheetDialog.close();
  const target = S.request ? $("[data-request]") : document.getElementById(`step-${S.reached}`);
  target?.scrollIntoView({ block: "start" });
  (target?.querySelector("[data-continue]") || target?.querySelector("h2"))?.focus({ preventScroll: true });
};
$("[data-bar-continue]").addEventListener("click", goCurrent);
$("[data-sheet-continue]").addEventListener("click", goCurrent);
$("[data-start-over]").addEventListener("click", () => {
  const years = S.years;
  const mode = S.mode;
  S = fresh();
  S.years = years;
  S.mode = mode;
  if (mode === "offline") S.vehicle.showCards = true;
  picker = null;
  render();
  window.scrollTo({ top: 0 });
});

// Start ----------------------------------------------------------------------

async function start() {
  const params = new URLSearchParams(location.search);
  render();
  try {
    S.years = (await get("vehicles/years")).years;
  } catch (error) {
    return failed(error);
  }
  if (params.get("year") && params.get("make") && params.get("model")) {
    S.vehicle.year = params.get("year");
    S.vehicle.make = params.get("make");
    S.vehicle.model = params.get("model");
    S.vehicle.type = params.get("type") === "motorcycle" ? "motorcycle" : "vehicle";
    await loadMakes();
    await loadModels();
    await lookUp();
  }
  render();
}

start();
