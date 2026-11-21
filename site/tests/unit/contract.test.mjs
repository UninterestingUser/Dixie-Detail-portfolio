// The fake API (tests/fake/api.mjs) answers with the real API's shapes, as
// data/public-api-shapes.yaml records them. app/publicapi/test_contract.py
// checks the real API against the same file, so the fake the browser tests
// run on can't drift from the real API again: the fake once added a `place`
// field to its quotes, the booking flow relied on it, and the real location
// step never unlocked.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { parse } from "yaml";
import { createFakeApi, GOOD_TOKEN } from "../fake/api.mjs";

const shapes = parse(readFileSync(new URL("../../../data/public-api-shapes.yaml", import.meta.url), "utf8")).answers;

const typeOf = (value) => (value === null ? "null" : Array.isArray(value) ? "list" : typeof value);

// Every way value differs from shape, as "path: problem" lines.
export function mismatches(value, shape, path = "answer") {
  if (typeof shape === "string") {
    if (shape === "any") return [];
    return shape.split("|").includes(typeOf(value)) ? [] : [`${path}: a ${typeOf(value)}, not ${shape}`];
  }
  if (Array.isArray(shape) || (shape && "$items" in shape)) {
    if (value === null && !Array.isArray(shape)) return [];
    if (!Array.isArray(value)) return [`${path}: a ${typeOf(value)}, not a list`];
    const item = Array.isArray(shape) ? shape[0] : shape.$items;
    return value.flatMap((element, i) => mismatches(element, item, `${path}[${i}]`));
  }
  if (value === null && shape.$or_null) return [];
  if (typeOf(value) !== "object") return [`${path}: a ${typeOf(value)}, not an object`];
  const keys = new Map(Object.entries(shape).filter(([key]) => key !== "$or_null").map(([key, element]) => [key.replace(/\?$/, ""), { element, optional: key.endsWith("?") }]));
  const problems = [];
  for (const [name, { element, optional }] of keys) {
    if (!(name in value)) {
      if (!optional) problems.push(`${path}.${name}: missing; the real API sends it`);
    } else problems.push(...mismatches(value[name], element, `${path}.${name}`));
  }
  for (const name of Object.keys(value)) if (!keys.has(name)) problems.push(`${path}.${name}: the real API never sends it`);
  return problems;
}

let server;
let base;
before(async () => {
  const fake = createFakeApi();
  server = createServer((req, res) => fake.handle(req, res));
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}/api/public/v1/`;
});
after(() => server.close());

async function call(path, { body, params, form } = {}) {
  const query = params ? "?" + new URLSearchParams(params) : "";
  const options = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : form ? { method: "POST", body: form } : {};
  const response = await fetch(base + path + query, options);
  return { status: response.status, body: await response.json() };
}

function fits(name, answer, status, expected) {
  assert.equal(answer.status, expected, `${name}: HTTP ${answer.status} ${JSON.stringify(answer.body)}`);
  assert.ok(shapes[name], `${name} is in public-api-shapes.yaml`);
  assert.deepEqual(mismatches(answer.body, shapes[name]), [], `${name} has the real API's shape`);
}

test("the shape checker finds a missing, an extra and a wrongly typed field", () => {
  const shape = { a: "string", "b?": "number", c: { $or_null: true, d: ["boolean"] } };
  assert.deepEqual(mismatches({ a: "x", c: null }, shape), []);
  assert.deepEqual(mismatches({ a: 1, c: { d: [true, "no"] }, place: "P1" }, shape), [
    "answer.a: a number, not string",
    "answer.c.d[1]: a string, not boolean",
    "answer.place: the real API never sends it",
  ]);
  assert.deepEqual(mismatches({ c: null }, shape), ["answer.a: missing; the real API sends it"]);
});

test("every fake answer the website reads has the real API's shape", async () => {
  fits("services", await call("services"), 200, 200);
  fits("booking-options", await call("booking-options"), 200, 200);
  fits("price-table", await call("price-table"), 200, 200);
  fits("reviews", await call("reviews"), 200, 200);
  fits("vehicles/years", await call("vehicles/years"), 200, 200);
  fits("vehicles/makes", await call("vehicles/makes", { params: { year: 2019 } }), 200, 200);
  fits("vehicles/models", await call("vehicles/models", { params: { year: 2019, make: "Toyota" } }), 200, 200);
  fits("vehicles/models", await call("vehicles/models", { params: { year: 2020, make: "Honda" } }), 200, 200);
  for (const params of [
    { year: 2019, make: "Toyota", model: "RAV4" },
    { year: 2019, make: "Toyota", model: "Highlander" },
    { year: 2019, make: "Toyota", model: "Highlander", size: 3 },
    { year: 2020, make: "Honda", model: "Gold Wing", type: "motorcycle" },
    { year: 2021, make: "Ford", model: "Transit 250" },
    { year: 1969, make: "Chevrolet", model: "Camaro" },
  ]) fits("vehicles/lookup", await call("vehicles/lookup", { params }), 200, 200);
  fits("vehicles/photo-cards", await call("vehicles/photo-cards"), 200, 200);

  const place = await call("addresses", { body: { place_id: "ChIJfakeCleveland00001", session_token: "session-1" } });
  fits("addresses", place, 201, 201);
  fits("error", await call("addresses", { body: { place_id: "ChIJfakeKnoxville00001" } }), 422, 422);

  const rav4 = { year: 2019, make: "Toyota", model: "RAV4" };
  fits("quotes", await call("quotes", { body: { vehicle: rav4, service: 10, condition: 1, add_ons: [21] } }), 201, 201);
  fits("quotes", await call("quotes", { body: { vehicle: { photo_card: 1 }, service: 12, size: 2 } }), 201, 201);
  fits("quotes", await call("quotes", { body: { vehicle: { year: 2020, make: "Honda", model: "Gold Wing", type: "motorcycle" }, service: 17 } }), 201, 201);
  const quote = await call("quotes", { body: { vehicle: rav4, service: 10, condition: 2, add_ons: [21], place: place.body.place } });
  fits("quotes", quote, 201, 201);
  fits("error", await call("quotes", { body: { vehicle: rav4 } }), 400, 400);

  const times = await call("open-times", { params: { quote: quote.body.number, days: 31 } });
  fits("open-times", times, 200, 200);
  const start = times.body.days.find((day) => day.times.length).times[0].start;
  const consents = { version: "2026-11-18", appointment: true };
  fits("bookings", await call("bookings", { body: { quote: quote.body.number, start, first_name: "Jordan", mobile: "(423) 555-0142", payment_method: "cash", consents, turnstile: GOOD_TOKEN } }), 201, 201);
  // A booking taken as a request (decision 0113).
  const mode = (data) => fetch(new URL("/__fake/mode", base), { method: "POST", body: JSON.stringify(data) });
  await mode({ requested: true });
  const second = await call("quotes", { body: { vehicle: rav4, service: 10, condition: 1, place: place.body.place } });
  fits("bookings-requested", await call("bookings", { body: { quote: second.body.number, start, first_name: "Jordan", mobile: "(423) 555-0142", payment_method: "cash", consents, turnstile: GOOD_TOKEN } }), 202, 202);
  await mode({ requested: false });

  const session = await call("quote-requests/uploads", { body: { turnstile: GOOD_TOKEN } });
  fits("quote-requests/uploads", session, 201, 201);
  const form = new FormData();
  form.append("photo", new Blob([new Uint8Array([0xff, 0xd8, 0xff])], { type: "image/jpeg" }), "photo.jpg");
  const photo = await call(`quote-requests/uploads/${session.body.session}/photos`, { form });
  fits("quote-requests/uploads/photos", photo, 201, 201);
  const request = { vehicle: { year: 2021, make: "Ford", model: "Transit 250" }, service: "not_sure", description: "Work van.", place: place.body.place, first_name: "Morgan", mobile: "423-555-0160", consents, turnstile: GOOD_TOKEN };
  fits("quote-requests", await call("quote-requests", { body: { ...request, session: session.body.session, photos: [photo.body.photo] } }), 201, 201);
  fits("error", await call("quote-requests", { body: { ...request, turnstile: "refused" } }), 403, 403);
});
