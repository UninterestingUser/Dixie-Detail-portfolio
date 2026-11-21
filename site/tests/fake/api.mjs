// A fake of the public API (docs/reference/public-api.md), for building the
// site and for the browser tests. Its answers have the real API's shapes,
// as data/public-api-shapes.yaml records them (tests/unit/contract.test.mjs
// checks; app/publicapi/test_contract.py checks the real API against the
// same file), with invented prices and places. Anything the fake must keep
// that the real answer doesn't carry, such as a quote's place, is kept in
// its state, never added to an answer. Every total it gives is its own, and in
// "odd" mode deliberately differs from the sum of its lines, so a test can
// prove the page shows the server's numbers and works none out itself.
//
// Control endpoints, for the tests only:
//   POST /__fake/mode {"offline": true, "odd": true, "outage": false,
//                      "requested": true, "known": true}
//     requested: every booking is taken as a request, answered 202 (decision 0113);
//     known: bookings come back "confirmed", as for a known customer (decision 0112).
//   GET  /__fake/log    what was sent to the API and the offline piece
//   POST /__fake/reset

const BASE = "/api/public/v1/";

const CLASSES = [
  { id: 1, name: "Small", booked_by_quote: false, photo_card: "Small cars, small crossovers and two-seaters", examples: ["Civic", "Corolla"], sizes: [{ value: 1, label: "one row" }, { value: 2, label: "two rows" }] },
  { id: 2, name: "Medium", booked_by_quote: false, photo_card: "Midsize crossovers and small three-row vehicles", examples: ["RAV4", "CR-V"], sizes: [{ value: 2, label: "two rows" }, { value: 3, label: "three rows" }] },
  { id: 3, name: "Large", booked_by_quote: false, photo_card: "Midsize SUVs and minivans", examples: ["Highlander", "Pilot"], sizes: [{ value: 2, label: "two rows" }, { value: 3, label: "three rows" }] },
  { id: 5, name: "Full-size Vans", booked_by_quote: true, photo_card: "Ask for a quote", examples: [], sizes: [] },
  { id: 8, name: "Motorcycles", booked_by_quote: false, photo_card: "Motorcycles", examples: [], sizes: [] },
];

// In the real API's order: by kind, then name (catalog.pricebook).
const SERVICES = [
  { id: 20, name: "Carpet Extraction", kind: "add_on", description: "Carpets", condition_applies: false },
  { id: 15, name: "Headlight Restoration", kind: "add_on", description: "Both headlights", condition_applies: false },
  { id: 21, name: "Seat Extraction", kind: "add_on", description: "Cloth seats", condition_applies: false },
  { id: 13, name: "1-Step Paint Correction", kind: "service", description: "One-step polish", condition_applies: false },
  { id: 14, name: "2-Step Paint Correction", kind: "service", description: "Two-step polish", condition_applies: false },
  { id: 12, name: "Exterior Only", kind: "service", description: "The exterior half", condition_applies: false },
  { id: 10, name: "Full Detail", kind: "service", description: "Inside and out", condition_applies: true },
  { id: 11, name: "Interior Only", kind: "service", description: "The interior half", condition_applies: true },
  { id: 17, name: "Motorcycle Detail", kind: "service", description: "A motorcycle detailed", condition_applies: false },
];

// Invented reviews, in the owner's order: never a real customer's.
const REVIEWS = [
  { name: "Alex T.", text: "Invented review one. The truck looks new again.", date: "2026-11-02", stars: 5, link: "https://g.co/kgs/example-1" },
  { name: "Sam R.", text: "Invented review two, with no rating.", date: "2026-10-20", stars: null, link: null },
  { name: "Jo M.", text: "Invented review three.", date: "2026-10-05", stars: 4, link: null },
  { name: "Chris P.", text: "Invented review four, on the reviews page only.", date: "2026-09-12", stars: 5, link: null },
];

// The services each add-on goes with, as the real pricebook keeps them
// (decision 0106).
const GOES_WITH = { 15: [10, 12, 13, 14], 20: [10, 11], 21: [10, 11] };
const goesWith = (serviceId, addOnId) => (GOES_WITH[addOnId] || []).includes(serviceId);

// [service id, class id, size or null, price, one-person minutes on site]
const CELLS = [
  [10, 1, 1, "200.00", 240], [10, 1, 2, "230.00", 300], [10, 2, 2, "250.00", 300], [10, 2, 3, "270.00", 360], [10, 3, 2, "280.00", 360], [10, 3, 3, "310.00", 420],
  [11, 1, 1, "110.00", 150], [11, 1, 2, "130.00", 180], [11, 2, 2, "160.00", 210], [11, 2, 3, "180.00", 240], [11, 3, 2, "175.00", 240], [11, 3, 3, "195.00", 270],
  [12, 1, null, "110.00", 150], [12, 2, null, "120.00", 150], [12, 3, null, "140.00", 180],
  [13, 1, null, "300.00", 420], [13, 2, null, "350.00", 450], [13, 3, null, "400.00", 480],
  [14, 1, null, "450.00", 540], [14, 2, null, "550.00", 570], [14, 3, null, "625.00", 600],
  [15, 1, null, "95.00", 150], [15, 2, null, "95.00", 150], [15, 3, null, "95.00", 150],
  [17, 8, null, "100.00", 180],
  [20, 1, 1, "50.00", 60], [20, 1, 2, "70.00", 90], [20, 2, 2, "70.00", 90], [20, 2, 3, "90.00", 120], [20, 3, 2, "70.00", 90], [20, 3, 3, "90.00", 120],
  [21, 1, 1, "60.00", 60], [21, 1, 2, "80.00", 90], [21, 2, 2, "80.00", 90], [21, 2, 3, "100.00", 120], [21, 3, 2, "80.00", 90], [21, 3, 3, "100.00", 120],
];

const LEVELS = [
  { level: 1, adds_percent: "0", booked_by_quote: false, label: "", description: "" },
  { level: 2, adds_percent: "10", booked_by_quote: false, label: "Needs attention", description: "" },
  { level: 3, adds_percent: null, booked_by_quote: true, label: "", description: "" },
];

const MODELS = {
  Toyota: [["RAV4", "vehicle"], ["Highlander", "vehicle"]],
  Honda: [["Accord", "vehicle"], ["Gold Wing", "motorcycle"]],
  Ford: [["Transit 250", "vehicle"]],
};
const LOOKUP = {
  RAV4: { class_id: 2, size: 2 },
  Highlander: { class_id: 3, question: { key: "third_row", text: "Does it have the optional third row?", choices: [{ answer: 2, label: "Two rows" }, { answer: 3, label: "Third row" }] } },
  Accord: { class_id: 1, size: 2 },
  "Gold Wing": { class_id: 8, size: null, motorcycle: true },
  "Transit 250": { class_id: 5, size: null },
};

export const PLACES = {
  ChIJfakeCleveland00001: { line1: "100 Example St NW", city: "Cleveland", state: "TN", zip_code: "37311", in: true, rate: "9.75", jurisdiction: "Cleveland" },
  ChIJfakeKnoxville00001: { line1: "1 Made Up Ave", city: "Knoxville", state: "TN", zip_code: "37919", in: false },
};

const CONSENT = {
  version: "2026-11-18",
  appointment: "I agree to receive text messages from Dixie Detail about my appointment at the number I provided, including confirmations, reminders, arrival updates, payment links, receipts and a review request after the service. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. See our Privacy Policy and Text Message Terms.",
  links: { privacy_policy: "https://dixiedetail.com/privacy-policy/", text_message_terms: "https://dixiedetail.com/sms-terms/" },
};

export const GOOD_TOKEN = "fake-turnstile-token";

const classById = (id) => CLASSES.find((item) => item.id === id);
const serviceById = (id) => SERVICES.find((item) => item.id === id);
function cell(serviceId, classId, size) {
  return CELLS.find((c) => c[0] === serviceId && c[1] === classId && (c[2] === size || c[2] === null));
}
// Cents as an integer, only inside the fake (it plays the server).
const cents = (text) => Math.round(Number(text) * 100);
const text = (value) => (value / 100).toFixed(2);

function pricebook() {
  const services = SERVICES.map((service) => {
    const prices = CELLS.filter((c) => c[0] === service.id).map((c) => ({ class_id: c[1], size: c[2], price: c[3] }));
    const from = prices.map((p) => p.price).sort((a, b) => cents(a) - cents(b))[0];
    const addOns = service.kind === "service" ? SERVICES.filter((item) => item.kind === "add_on" && goesWith(service.id, item.id)).map((item) => item.id) : [];
    return { ...service, add_ons: addOns, from_price: from, prices };
  });
  return {
    pricebook_version: 7,
    effective_date: "2026-11-14",
    classes: CLASSES.map((c) => {
      const mains = CELLS.filter((x) => x[1] === c.id && serviceById(x[0]).kind === "service").map((x) => x[3]).sort((a, b) => cents(a) - cents(b));
      return { id: c.id, name: c.name, booked_by_quote: c.booked_by_quote, photo_card: c.photo_card, examples: c.examples, sizes: c.sizes, from_price: mains[0] || null };
    }),
    condition_levels: LEVELS,
    services,
  };
}

function priceJob({ serviceId, classId, size, level, addOns, odd }) {
  const main = cell(serviceId, classId, size);
  if (!main) return null;
  const service = serviceById(serviceId);
  const lines = [{ kind: "service", description: service.name, amount: main[3] }];
  let total = cents(main[3]);
  let minutes = main[4];
  if (level === 2) {
    const add = Math.round(cents(main[3]) / 1000) * 100;
    lines.push({ kind: "condition", description: "Condition level 2 (+10%)", amount: text(add) });
    total += add;
    minutes += Math.round(main[4] / 10);
  }
  for (const id of addOns) {
    const extra = cell(id, classId, size);
    if (!extra) return null;
    lines.push({ kind: "add_on", description: serviceById(id).name, amount: extra[3] });
    total += cents(extra[3]);
    minutes += extra[4];
  }
  if (odd) total += 37; // A total no browser could work out from the lines.
  return { lines, total, minutes };
}

function priceTable() {
  const jobs = [];
  for (const c of CLASSES.filter((item) => !item.booked_by_quote)) {
    const sizes = c.sizes.length ? c.sizes.map((s) => s.value) : [null];
    for (const size of sizes) {
      for (const service of SERVICES.filter((s) => s.kind === "service")) {
        for (const level of service.condition_applies ? [1, 2] : [null]) {
          const offered = SERVICES.filter((item) => item.kind === "add_on" && goesWith(service.id, item.id)).map((item) => item.id);
          const sets = offered.reduce((found, id) => [...found, ...found.map((set) => [...set, id])], [[]]).map((set) => set.sort((a, b) => a - b));
          for (const addOns of sets) {
            const job = priceJob({ serviceId: service.id, classId: c.id, size, level, addOns });
            if (job) jobs.push({ class_id: c.id, size, service: service.id, condition: level, add_ons: addOns, total_before_tax: text(job.total), time_on_site_minutes: job.minutes, full_day: job.minutes >= 480 });
          }
        }
      }
    }
  }
  return { pricebook_version: 7, effective_date: "2026-11-14", jobs };
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}
const iso = (date) => date.toISOString().slice(0, 10);

export function createFakeApi() {
  const state = { mode: { offline: false, odd: false }, quotes: new Map(), quotePlaces: new Map(), places: new Map(), sessions: new Map(), log: [], counter: 0 };
  const next = (prefix) => `${prefix}${String(++state.counter).padStart(6, "0")}`;

  function lookup(params) {
    const model = params.get("model");
    const found = LOOKUP[model];
    const vehicle = { year: Number(params.get("year")), make: params.get("make"), model, motorcycle: !!(found && found.motorcycle) };
    if (!found) return { vehicle, photo_cards: cards(), class: null, size: null, question: null, booked_by_quote: false, message: "Pick the picture closest to your vehicle." };
    const c = classById(found.class_id);
    let size = found.size ? c.sizes.find((s) => s.value === found.size) : null;
    let question = found.question || null;
    const answered = params.get("size");
    if (question && answered) { size = c.sizes.find((s) => s.value === Number(answered)); question = null; }
    return {
      vehicle, photo_cards: null, class: { id: c.id, name: c.name, booked_by_quote: c.booked_by_quote }, size, question, booked_by_quote: c.booked_by_quote,
      message: c.booked_by_quote ? `${c.name} are priced by hand. Ask for a quote and we'll reply with a price.` : `${c.name} identified.`,
    };
  }

  function cards() {
    return CLASSES.map((c) => ({ class_id: c.id, name: c.name, caption: c.photo_card, examples: c.examples, photo: null, booked_by_quote: c.booked_by_quote }));
  }

  function resolveVehicle(vehicle, size) {
    if (vehicle.photo_card) {
      const c = classById(vehicle.photo_card);
      if (!c) return { error: [400, { error: "bad_request", field: "vehicle.photo_card", message: "Something in the form isn't right." }] };
      if (c.sizes.length > 1 && !size) return { error: [422, { error: "size_question", message: "Which fits it best?", question: { key: "size", text: "Which fits it best?", choices: c.sizes.map((s) => ({ answer: s.value, label: s.label })) } }] };
      return { c, size: c.sizes.length === 1 ? c.sizes[0].value : size || null, text: `${c.name} (picked from the photo cards)` };
    }
    const found = LOOKUP[vehicle.model];
    if (!found) return { error: [422, { error: "photo_card_needed", message: "Pick the picture closest to your vehicle.", photo_cards: cards() }] };
    const c = classById(found.class_id);
    if (found.question && !size) return { error: [422, { error: "size_question", message: found.question.text, question: found.question }] };
    return { c, size: found.size || size || null, text: `${vehicle.year} ${vehicle.make} ${vehicle.model}` };
  }

  function quote(body) {
    const vehicle = resolveVehicle(body.vehicle, body.size);
    if (vehicle.error) return vehicle.error;
    const { c, size } = vehicle;
    if (c.booked_by_quote) return [422, { error: "ask_for_quote", message: `${c.name} are priced by hand. Ask for a quote and we'll reply with a price.` }];
    const service = serviceById(body.service);
    if (!service || service.kind !== "service") return [400, { error: "bad_request", field: "service", message: "Something in the form isn't right." }];
    if (!service.condition_applies && body.condition != null) return [400, { error: "bad_request", field: "condition", message: "Only Full Detail and Interior Only take a condition level." }];
    if (service.condition_applies && body.condition == null) return [400, { error: "bad_request", field: "condition", message: "Pick the vehicle's condition." }];
    const addOns = body.add_ons || [];
    const unfit = addOns.filter((id) => !goesWith(service.id, id));
    if (unfit.length) return [400, { error: "bad_request", field: "add_ons", message: `${unfit.map((id) => serviceById(id).name).join(" and ")} can't be added to ${service.name}.` }];
    if (body.condition === 3) return [422, { error: "ask_for_quote", message: `${service.name} at condition level 3 is priced by hand. Ask for a quote and we'll reply with a price.`, quote_request: { service: service.id, condition: 3, add_ons: addOns } }];
    const job = priceJob({ serviceId: service.id, classId: c.id, size, level: body.condition, addOns, odd: state.mode.odd });
    if (!job) return [422, { error: "not_offered", message: "That service or add-on isn't offered for this vehicle." }];
    const place = body.place ? state.places.get(body.place) : null;
    const minutes = job.minutes;
    const tax = place ? Math.round(job.total * 0.0975) : 0;
    const number = next("Q").padEnd(10, "X");
    const web = {
      number,
      expires_at: new Date(Date.now() + 7200000).toISOString(),
      pricebook_version: 7,
      vehicle: { description: vehicle.text, class: { id: c.id, name: c.name, booked_by_quote: false }, size: size ? c.sizes.find((s) => s.value === size) || null : null },
      service: { id: service.id, name: service.name },
      add_ons: addOns.map((id) => ({ id, name: serviceById(id).name })),
      condition_level: service.condition_applies ? body.condition : null,
      lines: job.lines,
      total_before_tax: text(job.total),
      address: place ? `${place.line1}, ${place.city}, ${place.state} ${place.zip_code}` : null,
      sales_tax: place ? { rate_percent: place.rate, amount: text(tax), jurisdiction: place.jurisdiction } : null,
      total: text(job.total + tax),
      service_minutes: minutes - 60,
      time_on_site_minutes: minutes,
      full_day: minutes >= 480,
    };
    state.quotes.set(number, web);
    // Which place the quote was for, kept by the fake as the server keeps
    // it: the real quote answer has no place field.
    if (place) state.quotePlaces.set(number, body.place);
    return [201, web];
  }

  function openTimes(params) {
    const web = state.quotes.get(params.get("quote"));
    if (!web) return [404, { error: "not_found", message: "That quote wasn't found." }];
    if (!state.quotePlaces.has(web.number)) return [422, { error: "address_needed", message: "Enter the service address first." }];
    const today = new Date();
    const first = params.get("from") ? new Date(params.get("from") + "T12:00:00") : addDays(today, 2);
    const days = [];
    for (let i = 0; i < Number(params.get("days") || 14); i++) {
      const day = addDays(first, i);
      const date = iso(day);
      // Like the real API: every day in the window, a closed one with no times.
      if (day.getDay() === 0 || day.getDate() % 5 === 0) { days.push({ date, times: [] }); continue; }
      days.push({ date, times: ["08:00", "08:30", "09:00"].map((t) => ({ start: `${date}T${t}:00-05:00`, label: t === "08:00" ? "8:00 AM" : t === "08:30" ? "8:30 AM" : "9:00 AM" })) });
    }
    return [200, { quote: web.number, expired: false, from: iso(first), to: iso(addDays(first, 30)), days }];
  }

  function book(body) {
    if (body.turnstile !== GOOD_TOKEN) return [403, { error: "turnstile_failed", message: "We couldn't confirm you're a person. Please try again." }];
    const web = state.quotes.get(body.quote);
    if (!web) return [404, { error: "not_found", message: "That quote wasn't found." }];
    for (const key of ["first_name", "mobile", "payment_method", "consents", "start"]) {
      if (body[key] == null) return [400, { error: "bad_request", field: key, message: "Something in the form isn't right." }];
    }
    // "confirmed" for a known customer (mode.known), else how they confirm (decision 0112).
    const confirmation = state.mode.known ? "confirmed" : body.consents.appointment ? "text" : "call";
    const reference = next("B").padEnd(8, "K");
    const summary = {
      service: web.service.name, add_ons: web.add_ons.map((a) => a.name), vehicle: web.vehicle.description, color: body.color || "",
      date: body.start.slice(0, 10), arrival: "the day you picked", time_on_site: web.full_day ? "Full day" : `${web.time_on_site_minutes / 60} hours`,
      address: web.address, total_before_tax: web.total_before_tax, sales_tax: web.sales_tax ? web.sales_tax.amount : "0.00", total: web.total,
      payment_method: body.payment_method, notes: ["The final price is confirmed when we see the vehicle.", "Nothing is charged until the job is done.", "Please have water and power available near the vehicle."],
    };
    // A booking that becomes a request (decision 0113): one answer, whatever the reason.
    if (state.mode.requested) {
      const request = next("R").padEnd(8, "Q");
      return [202, { request, status: "requested", message: `Thanks! We've got your request for this time. We'll confirm it by text or call. Your request number is ${request}.`, summary }];
    }
    return [201, { reference, confirmation, summary, calendar_file: { name: `dixie-detail-${reference}.ics`, content_type: "text/calendar", content: "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Dixie Detail\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n" } }];
  }

  async function readBody(req) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    return Buffer.concat(chunks);
  }

  function send(res, status, body) {
    res.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS" });
    res.end(JSON.stringify(body));
  }

  async function handle(req, res) {
    const url = new URL(req.url, "http://fake");
    if (req.method === "OPTIONS") return send(res, 204, {});
    if (url.pathname === "/__fake/mode") { Object.assign(state.mode, JSON.parse((await readBody(req)).toString() || "{}")); return send(res, 200, state.mode); }
    if (url.pathname === "/__fake/log") return send(res, 200, state.log);
    if (url.pathname === "/__fake/reset") { state.mode = { offline: false, odd: false, requested: false, known: false }; state.log = []; return send(res, 200, {}); }

    // The Cloudflare offline piece, as the site calls it (functions/offline).
    if (url.pathname.startsWith("/offline/")) {
      const body = JSON.parse((await readBody(req)).toString());
      state.log.push({ to: url.pathname, body });
      if (body.turnstile !== GOOD_TOKEN) return send(res, 403, { error: "turnstile_failed", message: "We couldn't confirm you're a person." });
      return send(res, 202, { held: true });
    }
    if (!url.pathname.startsWith(BASE)) return false;
    if (state.mode.offline) { req.socket.destroy(); return true; }
    const path = url.pathname.slice(BASE.length);
    const raw = req.method === "POST" && !path.endsWith("/photos") ? (await readBody(req)).toString() : "";
    const body = raw ? JSON.parse(raw) : {};
    if (req.method !== "GET") state.log.push({ to: path, method: req.method, body: path.endsWith("/photos") ? "photo" : body });
    const p = url.searchParams;
    if (path === "services") return send(res, 200, pricebook());
    if (path === "price-table") return send(res, 200, priceTable());
    if (path === "reviews") return send(res, 200, { reviews: REVIEWS });
    if (path === "booking-options") return send(res, 200, {
      payment_methods: [["cash", "Cash"], ["card", "Card"], ["venmo", "Venmo"], ["paypal", "PayPal"], ["cash_app", "Cash App"], ["bitcoin", "Bitcoin"]].map(([value, label]) => ({ value, label })),
      consent: CONSENT, quote_lifetime_minutes: 120, photos: { max_per_request: 6, max_megabytes: 15, types: ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"] },
    });
    if (path === "vehicles/years") return send(res, 200, { years: [2026, 2025, 2024, 2021, 2020, 2019, 2018, 2015], first_year: 1984 });
    if (path === "vehicles/makes") return send(res, 200, { year: Number(p.get("year")), makes: Object.keys(MODELS).sort() });
    if (path === "vehicles/models") return send(res, 200, { year: Number(p.get("year")), make: p.get("make"), models: (MODELS[p.get("make")] || []).map(([name, type]) => ({ name, type, motorcycle: type === "motorcycle" })) });
    if (path === "vehicles/lookup") return send(res, 200, lookup(p));
    if (path === "vehicles/photo-cards") return send(res, 200, { photo_cards: cards() });
    if (path === "addresses") {
      const place = PLACES[body.place_id];
      if (!place) return send(res, 422, { error: "not_an_address", message: "That doesn't look like a street address." });
      if (!place.in) return send(res, 422, { error: "outside_area", message: "Sorry, that address is outside the area we serve. If you think we can still help, call or text (423) 380-9120." });
      const token = next("P");
      state.places.set(token, place);
      return send(res, 201, { place: token, address: { line1: place.line1, line2: "", city: place.city, state: place.state, zip_code: place.zip_code, one_line: `${place.line1}, ${place.city}, ${place.state} ${place.zip_code}` }, in_area: true, approved_out_of_area: false, tax: { rate_percent: place.rate, jurisdiction: place.jurisdiction }, reminder: "We bring everything else, but we need water and power at the vehicle." });
    }
    if (path === "quotes") { const [status, answer] = quote(body); return send(res, status, answer); }
    if (path === "open-times") { const [status, answer] = openTimes(p); return send(res, status, answer); }
    if (path === "bookings") { const [status, answer] = book(body); return send(res, status, answer); }
    if (path === "quote-requests/uploads") {
      if (body.turnstile !== GOOD_TOKEN) return send(res, 403, { error: "turnstile_failed", message: "We couldn't confirm you're a person." });
      const session = next("S");
      state.sessions.set(session, []);
      return send(res, 201, { session, expires_at: new Date(Date.now() + 6 * 3600000).toISOString(), max_photos: 6, max_megabytes: 15 });
    }
    const photo = path.match(/^quote-requests\/uploads\/([^/]+)\/photos(?:\/([^/]+))?$/);
    if (photo) {
      if (req.method === "DELETE") return send(res, 200, { deleted: true });
      await readBody(req);
      return send(res, 201, { photo: next("F"), width: 640, height: 480 });
    }
    if (path === "quote-requests") {
      if (body.turnstile !== GOOD_TOKEN) return send(res, 403, { error: "turnstile_failed", message: "We couldn't confirm you're a person." });
      const reference = next("R").padEnd(8, "Q");
      return send(res, 201, { reference, photos: (body.photos || []).length, message: `Thanks! We've got your request and will reply with a price, usually within a day. Your request number is ${reference}.` });
    }
    return send(res, 404, { error: "not_found", message: "Not here." });
  }

  return { handle, state };
}
