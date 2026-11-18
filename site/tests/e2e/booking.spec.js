// The booking flow in a browser, against the fake API (docs/reference/booking-flow.md).
import { expect, test } from "@playwright/test";

async function fake(request, mode = {}) {
  await request.post("/__fake/reset");
  await request.post("/__fake/mode", { data: mode });
}

async function log(request) {
  return (await request.get("/__fake/log")).json();
}

async function pickVehicle(page, year, make, model) {
  await page.goto("/book/");
  await page.getByLabel("Year").selectOption(String(year));
  await page.getByLabel("Make").selectOption(make);
  await page.getByLabel("Model", { exact: true }).selectOption(model);
}

const estimate = (page) => page.locator("aside[data-estimate]");
const cont = (page, n) => page.locator(`[data-continue="${n}"]`);

async function address(page, text, pick) {
  await page.getByRole("combobox", { name: "Service address" }).fill(text);
  await page.getByRole("option", { name: new RegExp(pick) }).click();
}

async function details(page) {
  await page.getByLabel("First name").fill("Jordan");
  await page.getByLabel("Mobile number").pressSequentially("4235550142");
  await page.getByRole("button", { name: "Card", exact: true }).click();
}

test.beforeEach(async ({ request }) => fake(request));

test("a car, from vehicle to the booked confirmation with its calendar file", async ({ page, request }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await expect(page.getByText("Medium identified")).toBeVisible();
  await page.getByLabel("Color (optional)").fill("silver");
  await cont(page, 1).click();

  // Service before condition; prices for the class and size.
  await expect(page.locator('[data-service="Full Detail"]')).toContainText("$250");
  await page.locator('[data-service="Full Detail"]').click();
  await page.locator('[data-add-on="Seat Extraction"]').check();
  await expect(estimate(page)).toContainText("$330.00");
  await cont(page, 2).click();

  // Condition: Level 1 preselected; Level 2 changes price and time, from the server.
  await expect(page.locator('[data-level="1"]')).toHaveAttribute("aria-pressed", "true");
  await page.locator('[data-level="2"]').click();
  await expect(estimate(page)).toContainText("Condition level 2 (+10%)");
  await expect(estimate(page)).toContainText("$355.00");
  await cont(page, 3).click();

  // Location: Google suggestions, then the tax from the server.
  await expect(estimate(page)).toContainText("Sales tax is added once we have your address.");
  await address(page, "100 Example", "100 Example St NW");
  await expect(page.getByText("In our service area.")).toBeVisible();
  await expect(estimate(page)).toContainText("Sales tax (9.75%)");
  await cont(page, 4).click();

  await page.locator("[data-day]").first().click();
  await page.locator("[data-time]").first().click();
  await cont(page, 5).click();

  // Details: the phone formats itself; consents start unchecked.
  await details(page);
  await expect(page.getByLabel("Mobile number")).toHaveValue("(423) 555-0142");
  await expect(page.locator("#consent-appointment")).not.toBeChecked();
  await expect(page.locator("#consent-follow-up")).not.toBeChecked();
  await expect(page.locator("#consent-appointment + .consent")).toContainText("Reply STOP to opt out");
  await page.locator("#consent-appointment").check();
  await cont(page, 6).click();

  await page.locator("[data-book]").click();
  await expect(page.getByRole("heading", { name: "You're booked" })).toBeVisible();
  const calendar = page.locator("[data-calendar-file]");
  await expect(calendar).toHaveAttribute("download", /\.ics$/);
  await expect(calendar).toHaveAttribute("href", /^data:text\/calendar/);

  const booking = (await log(request)).find((entry) => entry.to === "bookings");
  expect(booking.body).toMatchObject({ first_name: "Jordan", mobile: "(423) 555-0142", payment_method: "card", color: "silver", turnstile: "fake-turnstile-token" });
  expect(booking.body.consents).toMatchObject({ version: "2026-10-13", appointment: true, follow_up: false });
});

test("a motorcycle: one service, no add-ons, no condition step", async ({ page }) => {
  await pickVehicle(page, 2020, "Honda", "Gold Wing");
  await expect(page.getByText("Motorcycles identified")).toBeVisible();
  await cont(page, 1).click();
  await expect(page.locator("[data-service]")).toHaveCount(1);
  await expect(page.locator("[data-add-on]")).toHaveCount(0);
  await page.locator('[data-service="Motorcycle Detail"]').click();
  await expect(page.locator("[data-continue='2']")).toHaveText("Continue to location");
  await cont(page, 2).click();
  await expect(page.locator("#step-3")).toBeHidden();
  await expect(page.locator("#step-4")).toBeVisible();
  await expect(estimate(page)).toContainText("$100.00");
});

test("a service that doesn't cover the interior skips the condition step", async ({ page, request }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Exterior Only"]').click();
  await expect(estimate(page)).toContainText("$120.00");
  const quote = (await log(request)).find((entry) => entry.to === "quotes");
  expect(quote.body.condition).toBeUndefined();
  await cont(page, 2).click();
  await expect(page.locator("#step-3")).toBeHidden();
});

test("a vehicle not listed is picked from the photo cards", async ({ page }) => {
  await page.goto("/book/");
  await page.getByRole("button", { name: "My vehicle isn't listed" }).click();
  await page.getByRole("button", { name: /^Small/ }).click();
  await expect(cont(page, 1)).toHaveAttribute("aria-disabled", "true");
  await page.getByRole("button", { name: "Two rows" }).click();
  await expect(page.getByText("Small identified")).toBeVisible();
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await expect(estimate(page)).toContainText("$230.00");
});

test("an address outside the area is refused with a way to reach us", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Exterior Only"]').click();
  await cont(page, 2).click();
  await address(page, "1 Made Up", "1 Made Up Ave");
  await expect(page.getByRole("alert")).toContainText("outside the area we serve");
  await expect(cont(page, 4)).toHaveAttribute("aria-disabled", "true");
});

test("the page shows the server's total, never one it works out", async ({ page, request }) => {
  await fake(request, { odd: true });
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await page.locator('[data-add-on="Seat Extraction"]').check();
  // The lines are $250 and $80; the fake server says $330.37.
  await expect(estimate(page).locator("[data-total]")).toHaveText("$330.37");
  await expect(estimate(page)).not.toContainText("$330.00");
});

test("offline, the form becomes a request a time form with the built-in prices", async ({ page, request }) => {
  await fake(request, { offline: true });
  await page.goto("/book/");
  await expect(page.locator("[data-banner]")).toContainText("can't reach our booking system");
  await page.getByRole("button", { name: /^Medium/ }).click();
  await page.getByLabel("Year").fill("2019");
  await page.getByLabel("Make").fill("Toyota");
  await page.getByLabel("Model").fill("RAV4");
  await page.getByRole("button", { name: "Two rows" }).click();
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await page.locator('[data-add-on="Seat Extraction"]').check();
  await cont(page, 2).click();
  await page.locator('[data-level="2"]').click();
  // The server's own total for this job, baked in at build time.
  await expect(estimate(page).locator("[data-total]")).toHaveText("$355.00");
  await cont(page, 3).click();
  await address(page, "100 Example", "100 Example St NW");
  await cont(page, 4).click();
  const day = new Date();
  day.setDate(day.getDate() + 3);
  if (day.getDay() === 0) day.setDate(day.getDate() + 1);
  await page.getByLabel("Preferred day").fill(day.toISOString().slice(0, 10));
  await cont(page, 5).click();
  await details(page);
  await cont(page, 6).click();
  await page.locator("[data-book]").click();
  await expect(page.getByRole("heading", { name: "Request sent" })).toBeVisible();
  const held = (await log(request)).find((entry) => entry.to === "/offline/time-request");
  expect(held.body).toMatchObject({
    vehicle: { photo_card: 2, year: 2019, make: "Toyota", model: "RAV4" }, size: 2, service: 10, add_ons: [21], condition: 2,
    place_id: "ChIJfakeCleveland00001", shown: { total: "355.00", pricebook_version: 7 }, turnstile: "fake-turnstile-token",
  });
  expect(held.body.request_id).toMatch(/^[0-9a-f-]{36}$/);
});

test("when address suggestions fail, the form takes the address as typed and is held", async ({ page, request }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Exterior Only"]').click();
  await cont(page, 2).click();
  await request.post("/__fake/mode", { data: { outage: true } });
  await page.getByRole("combobox", { name: "Service address" }).fill("100 Example St");
  await expect(page.locator("[data-banner]")).toContainText("Address suggestions aren't working");
  await page.getByLabel("Service address").fill("100 Example St NW, Cleveland, TN 37311");
  await cont(page, 4).click();
  const day = new Date();
  day.setDate(day.getDate() + 3);
  if (day.getDay() === 0) day.setDate(day.getDate() + 1);
  await page.getByLabel("Preferred day").fill(day.toISOString().slice(0, 10));
  await cont(page, 5).click();
  await details(page);
  await cont(page, 6).click();
  await page.locator("[data-book]").click();
  await expect(page.getByRole("heading", { name: "Request sent" })).toBeVisible();
  const held = (await log(request)).find((entry) => entry.to === "/offline/time-request");
  expect(held.body.address).toBe("100 Example St NW, Cleveland, TN 37311");
  expect(held.body.place_id).toBeUndefined();
  expect(held.body.vehicle).toMatchObject({ photo_card: 2, year: 2019, make: "Toyota", model: "RAV4" });
});

test("a van leaves the flow for a quote request, with photos", async ({ page, request }) => {
  await pickVehicle(page, 2021, "Ford", "Transit 250");
  await expect(page.getByText("Full-size Vans are priced by hand.")).toBeVisible();
  await page.locator('[data-ask-quote="class"]').click();
  await expect(page.getByRole("heading", { name: "Tell us about the job" })).toBeVisible();
  await expect(page.getByText("Photos are optional, but they help us give you an accurate quote.")).toBeVisible();
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
  await page.setInputFiles("#qr-photos", [{ name: "one.png", mimeType: "image/png", buffer: png }, { name: "two.png", mimeType: "image/png", buffer: png }]);
  await expect(page.locator(".photo-tile .state", { hasText: "Added" })).toHaveCount(2);
  await page.getByRole("button", { name: "Remove two.png" }).click();
  await expect(page.locator(".photo-tile")).toHaveCount(1);
  await page.getByLabel("What do you need?").fill("Work van, 15 passenger, very dirty inside.");
  await address(page, "100 Example", "100 Example St NW");
  await page.getByLabel("First name").fill("Morgan");
  await page.getByLabel("Mobile number").pressSequentially("4235550160");
  await page.locator("[data-send-request]").click();
  await expect(page.getByRole("heading", { name: "Request sent" })).toBeVisible();
  await expect(page.getByText("will reply with a price")).toBeVisible();
  const sent = (await log(request)).find((entry) => entry.to === "quote-requests");
  expect(sent.body).toMatchObject({ vehicle: { year: 2021, make: "Ford", model: "Transit 250" }, service: "not_sure", description: "Work van, 15 passenger, very dirty inside." });
  expect(sent.body.photos).toHaveLength(1);
  expect(sent.body.session).toBeTruthy();
});

test("Service Level 3 leaves the flow for a quote request carrying the service, level and add-ons", async ({ page, request }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Interior Only"]').click();
  await page.locator('[data-add-on="Seat Extraction"]').check();
  await cont(page, 2).click();
  await page.locator('[data-level="3"]').click();
  await expect(estimate(page)).toContainText("Ask for a quote");
  await expect(estimate(page).locator("[data-total]")).toHaveCount(0);
  await page.locator('[data-ask-quote="level"]').click();
  await page.getByLabel("What do you need?").fill("Two dogs, heavy hair.");
  await address(page, "100 Example", "100 Example St NW");
  await page.getByLabel("First name").fill("Avery");
  await page.getByLabel("Mobile number").pressSequentially("4235550123");
  await page.locator("[data-send-request]").click();
  await expect(page.getByRole("heading", { name: "Request sent" })).toBeVisible();
  const sent = (await log(request)).find((entry) => entry.to === "quote-requests");
  expect(sent.body).toMatchObject({ service: 11, condition: 3, add_ons: [21], size: 2 });
  expect(sent.body.photos).toBeUndefined();
});

test("offline, a quote request is held without photos", async ({ page, request }) => {
  await fake(request, { offline: true });
  await page.goto("/book/");
  await page.getByRole("button", { name: /^Full-size Vans/ }).click();
  await page.locator('[data-ask-quote="class"]').click();
  await expect(page.getByText("Photos can't be sent just now")).toBeVisible();
  await expect(page.locator("#qr-photos")).toHaveCount(0);
  await page.getByLabel("What do you need?").fill("Conversion van.");
  await address(page, "100 Example", "100 Example St NW");
  await page.getByLabel("First name").fill("Morgan");
  await page.getByLabel("Mobile number").pressSequentially("4235550160");
  await page.locator("[data-send-request]").click();
  await expect(page.getByText("text them to (423) 380-9120")).toBeVisible();
  const held = (await log(request)).find((entry) => entry.to === "/offline/quote-request");
  expect(held.body).toMatchObject({ vehicle: { photo_card: 5 }, description: "Conversion van.", place_id: "ChIJfakeCleveland00001", turnstile: "fake-turnstile-token" });
});

test("on a phone the estimate is a bar that opens into a sheet @phone", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone only");
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await expect(page.locator("[data-bar-total]")).toHaveText("$250.00");
  await page.locator("[data-open-estimate]").click();
  await expect(page.locator("[data-sheet]")).toBeVisible();
  await expect(page.locator("[data-sheet]")).toContainText("Full Detail");
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.locator("[data-sheet]")).toBeHidden();
});

// Never hang (booking-flow.md, when a send fails) ------------------------------

const PHONE = "(423) 380-9120";

async function offlineVanRequest(page, request) {
  await fake(request, { offline: true });
  await page.goto("/book/");
  await page.getByRole("button", { name: /^Full-size Vans/ }).click();
  await page.locator('[data-ask-quote="class"]').click();
  await page.getByLabel("What do you need?").fill("Conversion van.");
  await address(page, "100 Example", "100 Example St NW");
  await page.getByLabel("First name").fill("Morgan");
  await page.getByLabel("Mobile number").pressSequentially("4235550160");
}

async function offlineTimeRequestToReview(page, request) {
  await fake(request, { offline: true });
  await page.goto("/book/");
  await page.getByRole("button", { name: /^Medium/ }).click();
  await page.getByLabel("Year").fill("2019");
  await page.getByLabel("Make").fill("Toyota");
  await page.getByLabel("Model").fill("RAV4");
  await page.getByRole("button", { name: "Two rows" }).click();
  await cont(page, 1).click();
  await page.locator('[data-service="Exterior Only"]').click();
  await cont(page, 2).click();
  await address(page, "100 Example", "100 Example St NW");
  await cont(page, 4).click();
  const day = new Date();
  day.setDate(day.getDate() + 3);
  if (day.getDay() === 0) day.setDate(day.getDate() + 1);
  await page.getByLabel("Preferred day").fill(day.toISOString().slice(0, 10));
  await cont(page, 5).click();
  await details(page);
  await cont(page, 6).click();
}

test("a Turnstile that can't start, as with an empty site key, brings the button back with the phone number", async ({ page, request }) => {
  await offlineTimeRequestToReview(page, request);
  await page.evaluate(() => localStorage.setItem("fake-turnstile", "throw"));
  await page.locator("[data-book]").click();
  await expect(page.locator("#step-7 .error")).toContainText(`call or text ${PHONE}`);
  await expect(page.locator("[data-book]")).toHaveText("Send my request");
  expect((await log(request)).filter((entry) => entry.to === "/offline/time-request")).toHaveLength(0);
  // Nothing typed is lost: the same form sends once Turnstile works.
  await page.evaluate(() => localStorage.removeItem("fake-turnstile"));
  await page.locator("[data-book]").click();
  await expect(page.getByRole("heading", { name: "Request sent" })).toBeVisible();
  const held = (await log(request)).find((entry) => entry.to === "/offline/time-request");
  expect(held.body).toMatchObject({ first_name: "Jordan", mobile: "(423) 555-0142", service: 12 });
});

test("a blank Turnstile token counts as a failure, and nothing is sent", async ({ page, request }) => {
  await offlineVanRequest(page, request);
  await page.evaluate(() => localStorage.setItem("fake-turnstile", "empty"));
  await page.locator("[data-send-request]").click();
  await expect(page.locator("[data-request] .error")).toContainText(`call or text ${PHONE}`);
  await expect(page.locator("[data-send-request]")).toHaveText("Send my request");
  await expect(page.getByLabel("What do you need?")).toHaveValue("Conversion van.");
  expect((await log(request)).filter((entry) => entry.to === "/offline/quote-request")).toHaveLength(0);
});

test("a Turnstile check that never answers gives up, and the button comes back", async ({ page, request }) => {
  await page.clock.install();
  await offlineVanRequest(page, request);
  await page.evaluate(() => localStorage.setItem("fake-turnstile", "hang"));
  await page.locator("[data-send-request]").click();
  await expect(page.locator("[data-send-request]")).toHaveText("Sending…");
  await page.clock.fastForward(46000);
  await expect(page.locator("[data-request] .error")).toContainText(`call or text ${PHONE}`);
  await expect(page.locator("[data-send-request]")).toHaveText("Send my request");
  await expect(page.getByLabel("Mobile number")).toHaveValue("(423) 555-0160");
});

test("an offline piece that never answers gives up, and the button comes back", async ({ page, request }) => {
  await page.clock.install();
  await offlineVanRequest(page, request);
  let reached;
  const asked = new Promise((resolve) => (reached = resolve));
  await page.route("**/offline/quote-request", () => reached()); // never answered
  await page.locator("[data-send-request]").click();
  await asked;
  await expect(page.locator("[data-send-request]")).toHaveText("Sending…");
  await page.clock.fastForward(21000);
  await expect(page.locator("[data-request] .error")).toContainText(`call or text ${PHONE}`);
  await expect(page.locator("[data-send-request]")).toHaveText("Send my request");
});

// Offline detection: any network failure, timeout or 5xx from the API.
// Cloudflare's own error pages, such as the 530 while the tunnel is down,
// carry no CORS headers, so from the real site the browser sees a network
// failure; here, on one origin, the 530 itself arrives. Both are offline.
for (const [name, answer] of [
  ["Cloudflare's 530 while the tunnel is down", (route) => route.fulfill({ status: 530, contentType: "text/html", body: "<html><body>Error 1033: Argo Tunnel error</body></html>" })],
  ["a 502", (route) => route.fulfill({ status: 502, contentType: "text/html", body: "Bad gateway" })],
  ["a network failure", (route) => route.abort("failed")],
]) {
  test(`${name} from the API switches the site to the offline form`, async ({ page }) => {
    await page.route("**/api/public/v1/**", answer);
    await page.goto("/book/");
    await expect(page.locator("[data-banner]")).toContainText("can't reach our booking system");
    await expect(page.getByRole("button", { name: /^Medium/ })).toBeVisible();
  });
}

test("an API that never answers switches the site to the offline form after its time limit", async ({ page }) => {
  await page.clock.install();
  await page.route("**/api/public/v1/**", () => {}); // never answered
  await page.goto("/book/");
  await page.clock.fastForward(16000);
  await expect(page.locator("[data-banner]")).toContainText("can't reach our booking system");
});

test("a 530 in the middle of a booking switches to the offline form and keeps the vehicle", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.route("**/api/public/v1/**", (route) => route.fulfill({ status: 530, contentType: "text/html", body: "Error 1033" }));
  await page.locator('[data-service="Full Detail"]').click();
  await expect(page.locator("[data-banner]")).toContainText("can't reach our booking system");
  await expect(page.locator('[data-service="Full Detail"]')).toBeVisible();
});

// The location step unlocks from the real API's answers: the quote names no
// place, so the flow remembers which place it asked about. The fake once
// added a place to its quotes, and this step never unlocked on staging.
test("the location step goes on to date and time once the address is checked", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Exterior Only"]').click();
  await cont(page, 2).click();
  await expect(cont(page, 4)).toHaveAttribute("aria-disabled", "true");
  await address(page, "100 Example", "100 Example St NW");
  await expect(page.getByText("In our service area.")).toBeVisible();
  await expect(estimate(page)).toContainText("Sales tax (9.75%)");
  await expect(cont(page, 4)).toHaveAttribute("aria-disabled", "false");
  await cont(page, 4).click();
  await expect(page.locator("#step-5")).toBeVisible();
  await expect(page.locator("[data-day]").first()).toBeVisible();
  await page.locator("[data-day]").first().click();
  await page.locator("[data-time]").first().click();
  await expect(cont(page, 5)).toHaveAttribute("aria-disabled", "false");
});
