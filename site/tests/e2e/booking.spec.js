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
  // The class is internal: no box names it, and the estimate card doesn't either.
  await expect(page.getByText("Medium")).toHaveCount(0);
  await page.getByLabel("Color").fill("silver");
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
  await expect(estimate(page)).toContainText("Needs Attention (+10%)");
  await expect(estimate(page)).not.toContainText("Condition level 2");
  await expect(estimate(page)).toContainText("$355.00");
  await cont(page, 3).click();

  // Location: Google suggestions, then the tax from the server.
  await expect(estimate(page)).toContainText("Sales tax is added once we have your address.");
  await address(page, "100 Example", "100 Example St NW");
  await expect(page.locator("[data-in-area]")).toHaveText("In our service area");
  await expect(estimate(page)).toContainText("Sales tax (9.75%)");
  await cont(page, 4).click();

  await expect(page.getByText("Crossed-out days")).toHaveCount(0);
  await page.locator("[data-day]").first().click();
  await page.locator("[data-time]").first().click();
  await cont(page, 5).click();

  // Details: the phone formats itself; the last name stays optional.
  await expect(page.getByText("Last name", { exact: true })).toBeVisible();
  await expect(page.getByText("Payment is due when the work is finished.")).toBeVisible();
  await details(page);
  await expect(page.getByLabel("Mobile number")).toHaveValue("(423) 555-0142");
  await cont(page, 6).click();

  // Review: the vehicle with its color, the services joined, the new
  // condition wording; one consent box, unchecked, next to the button.
  const review = page.locator("#step-7 .review-list");
  // No size: nobody was asked one for a RAV4.
  await expect(review).toContainText("2019 Toyota RAV4 (silver)");
  await expect(review).not.toContainText("two rows");
  await expect(review).toContainText("Full Detail + Seat Extraction");
  await expect(review).toContainText("Needs extra attention");
  await expect(review.locator("dt", { hasText: "Color" })).toHaveCount(0);
  await expect(page.locator("#consent-appointment")).not.toBeChecked();
  await expect(page.locator('#step-7 input[type="checkbox"]')).toHaveCount(1);
  await expect(page.locator("#consent-appointment + .consent")).toHaveText("I agree to receive text messages from Dixie Detail about my appointment at the number I provided, including confirmations, reminders, arrival updates, payment links, receipts and a review request after the service. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. See our Privacy Policy and Text Message Terms.");
  await expect(page.locator("#consent-appointment + .consent a")).toHaveText(["Privacy Policy", "Text Message Terms"]);
  await page.locator("#consent-appointment").check();

  await page.locator("[data-book]").click();
  await expect(page.getByRole("heading", { name: "You're booked" })).toBeVisible();
  const calendar = page.locator("[data-calendar-file]");
  await expect(calendar).toHaveAttribute("download", /\.ics$/);
  await expect(calendar).toHaveAttribute("href", /^data:text\/calendar/);

  const booking = (await log(request)).find((entry) => entry.to === "bookings");
  expect(booking.body).toMatchObject({ first_name: "Jordan", mobile: "(423) 555-0142", payment_method: "card", color: "silver", turnstile: "fake-turnstile-token" });
  expect(booking.body.consents).toEqual({ version: "2026-11-18", appointment: true });
});

test("each service offers only the add-ons that go with it, and Headlight Restoration is one", async ({ page, request }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await expect(page.locator('[data-service="Headlight Restoration"]')).toHaveCount(0);
  // No add-ons until a service is picked.
  await expect(page.locator("[data-add-on]")).toHaveCount(0);
  const offered = async () => (await page.locator("[data-add-on]").evaluateAll((boxes) => boxes.map((box) => box.dataset.addOn))).sort();
  await page.locator('[data-service="Full Detail"]').click();
  expect(await offered()).toEqual(["Carpet Extraction", "Headlight Restoration", "Seat Extraction"]);
  await page.locator('[data-add-on="Seat Extraction"]').check();
  await page.locator('[data-add-on="Headlight Restoration"]').check();
  await expect(estimate(page)).toContainText("$425.00");
  // Exterior Only takes Headlight Restoration only: Seat Extraction is dropped.
  await page.locator('[data-service="Exterior Only"]').click();
  expect(await offered()).toEqual(["Headlight Restoration"]);
  await expect(page.locator('[data-add-on="Headlight Restoration"]')).toBeChecked();
  await expect(estimate(page)).toContainText("$215.00");
  await page.locator('[data-service="Interior Only"]').click();
  expect(await offered()).toEqual(["Carpet Extraction", "Seat Extraction"]);
  await expect(page.locator("[data-add-on]:checked")).toHaveCount(0);
  const quotes = (await log(request)).filter((entry) => entry.to === "quotes");
  expect(quotes.at(-1).body.add_ons).toEqual([]);
  expect(quotes.some((entry) => entry.body.service === 12 && entry.body.add_ons.includes(21))).toBe(false);
});

test("a motorcycle: one service, no add-ons, no condition step", async ({ page }) => {
  await pickVehicle(page, 2020, "Honda", "Gold Wing");
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
  await expect(cont(page, 1)).toHaveAttribute("aria-disabled", "false");
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
  await expect(page.getByRole("alert")).toHaveText("Sorry, that address is outside the area we serve. If you think we can still help, call or text (423) 380-9120.");
  await expect(page.getByText("Address picked")).toHaveCount(0);
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
  await cont(page, 1).click();
  await expect(page.getByRole("heading", { name: "Tell us about the job" })).toBeVisible();
  await expect(page.getByText("Photos are optional, but helpful in providing an accurate estimate. Add up to 6 photos.")).toBeVisible();
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
  await cont(page, 3).click();
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
  await cont(page, 1).click();
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
  await cont(page, 1).click();
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

test("a Turnstile check that never answers is tried four times, then gives up, and the button comes back", async ({ page, request }) => {
  await page.clock.install();
  await offlineVanRequest(page, request);
  await page.evaluate(() => localStorage.setItem("fake-turnstile", "hang"));
  await page.locator("[data-send-request]").click();
  await expect(page.locator("[data-send-request]")).toHaveText("Sending…");
  // Four tries of 15 seconds, 1.5 seconds apart, and nothing shown before.
  await page.clock.runFor(60000);
  await expect(page.locator("[data-request] .error")).toHaveCount(0);
  await page.clock.runFor(6000);
  expect(await page.evaluate(() => window.fakeTurnstileChecks)).toBe(4);
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
  await expect(page.locator("[data-in-area]")).toHaveText("In our service area");
  await expect(estimate(page)).toContainText("Sales tax (9.75%)");
  await expect(cont(page, 4)).toHaveAttribute("aria-disabled", "false");
  await cont(page, 4).click();
  await expect(page.locator("#step-5")).toBeVisible();
  await expect(page.locator("[data-day]").first()).toBeVisible();
  await page.locator("[data-day]").first().click();
  await page.locator("[data-time]").first().click();
  await expect(cont(page, 5)).toHaveAttribute("aria-disabled", "false");
});

// Acceptance changes B (owner, 2026-11-18) -----------------------------------

test("no step shows the text \"null\" once it's done, nor the quote request card", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Interior Only"]').click();
  await cont(page, 2).click();
  await cont(page, 3).click();
  await expect(page.locator("#step-4")).toBeVisible();
  for (const n of [1, 2, 3]) await expect(page.locator(`#step-${n}`)).not.toContainText("null");
  await page.locator('[data-level="3"]').click();
  await cont(page, 3).click();
  await expect(page.locator("[data-request]")).toBeVisible();
  await expect(page.locator("[data-request]")).not.toContainText("null");
});

test("a vehicle booked by quote: no class box, a note, and one \"Request quote\" button", async ({ page }) => {
  await pickVehicle(page, 2021, "Ford", "Transit 250");
  const step = page.locator("#step-1");
  await expect(step.locator("[data-quote-note]")).toHaveText("Full-size vans vary in size and condition.Request a quote and we'll reply with your estimate, usually within a day.");
  await expect(step.locator("[data-quote-note] strong")).toHaveText("Full-size vans vary in size and condition.");
  await expect(step.locator("[data-ask-quote]")).toHaveCount(0);
  await expect(step.getByText("priced by hand")).toHaveCount(0);
  await expect(cont(page, 1)).toHaveText("Request quote");
  await expect(cont(page, 1)).toHaveAttribute("aria-disabled", "false");
  await cont(page, 1).click();
  const card = page.locator("[data-request]");
  await expect(card.locator(".intro")).toHaveText("Full-size Vans vary in size and condition and require a manual estimate. Give us some details about the job and we'll reply with a price, usually within a day.");
  await expect(card.getByText("Provide relevant details about the vehicle (size, interior configuration, etc.) and what you need done.")).toBeVisible();
  await expect(card.getByText("Last name", { exact: true })).toBeVisible();
  await expect(card.getByLabel("Preferred days (optional)")).toHaveAttribute("placeholder", "Such as weekdays, a specific date, etc.");
  // The consent box sits just above "Send my request", unchecked.
  await expect(card.locator("#consent-appointment")).not.toBeChecked();
  const order = await card.evaluate((el) => [...el.querySelectorAll("#consent-appointment, [data-send-request]")].map((node) => node.id || "send"));
  expect(order).toEqual(["consent-appointment", "send"]);
});

test("Level 3 shows only the owner's note, and the one button reads \"Request quote\"", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await cont(page, 2).click();
  const step = page.locator("#step-3");
  await expect(step.locator("h2")).toHaveText("What is the condition of the interior?");
  await expect(step.locator(".choice .name")).toHaveText(["Normal wear and tear", "Needs extra attention", "Let's talk"]);
  await expect(cont(page, 3)).toHaveText("Continue to location");
  await page.locator('[data-level="3"]').click();
  await expect(step.locator("[data-quote-note]")).toHaveText("Unique situations require manual quoting. Hit the button below to tell us what you're dealing with and add photos if you can. We'll respond with a quote, usually within 24 hours.");
  await expect(step.getByText("Quoted by hand")).toHaveCount(0);
  await expect(step.locator("[data-ask-quote]")).toHaveCount(0);
  await expect(cont(page, 3)).toHaveText("Request quote");
  await cont(page, 3).click();
  await expect(page.locator("[data-request] .intro")).toHaveText("Unique situations require a manual estimate. Give us some details about the job and we'll reply with a price, usually within a day.");
  await page.getByRole("button", { name: "Back to booking" }).click();
  await page.locator('[data-level="2"]').click();
  await expect(cont(page, 3)).toHaveText("Continue to location");
});

test("step 2 lists the services in the owner's order, with the add-ons that fit as \"Available add-ons\"", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  const step = page.locator("#step-2");
  await expect(step.locator("h2")).toHaveText("Choose your service");
  await expect(step.locator("[data-service] .name")).toHaveText(["Full Detail", "Interior Only", "Exterior Only", "1-Step Paint Correction", "2-Step Paint Correction"]);
  await page.locator('[data-service="Exterior Only"]').click();
  await expect(step.getByRole("heading", { name: "Available add-ons" })).toBeVisible();
  // Headlight Restoration is an add-on, the only one with Exterior Only.
  await expect(step.locator("[data-add-on]")).toHaveCount(1);
  await expect(step.locator('[data-add-on="Headlight Restoration"]')).toBeVisible();
  await page.locator('[data-service="Interior Only"]').click();
  await expect(step.locator('[data-add-on="Headlight Restoration"]')).toHaveCount(0);
  await expect(step.locator("[data-add-on]")).toHaveCount(2);
});

test("the color and \"My vehicle isn't listed\" share a row, and the steps have a gap between them", async ({ page }) => {
  await page.goto("/book/");
  const color = await page.getByLabel("Color").boundingBox();
  const link = await page.getByRole("button", { name: "My vehicle isn't listed" }).boundingBox();
  expect(Math.abs(color.y - link.y)).toBeLessThan(60);
  expect(link.x).toBeGreaterThan(color.x + color.width);
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await expect(page.locator("#step-2")).toBeVisible();
  // Both boxes measured at once: the page scrolls to the new step.
  const gap = await page.evaluate(() => document.getElementById("step-2").getBoundingClientRect().top - document.getElementById("step-1").getBoundingClientRect().bottom);
  expect(gap).toBeGreaterThanOrEqual(10);
});

// Acceptance changes 2 (owner, 2026-11-18) -----------------------------------

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const twoPhotos = [{ name: "one.png", mimeType: "image/png", buffer: PNG }, { name: "two.png", mimeType: "image/png", buffer: PNG }];

test("a size question stays shown once answered, with the answer selected and changeable @phone", async ({ page }) => {
  await pickVehicle(page, 2020, "Toyota", "Highlander");
  const question = page.locator("[data-size-question]");
  await expect(question).toContainText("Does it have the optional third row?");
  await question.getByRole("button", { name: "Third row" }).click();
  await expect(question.getByRole("button", { name: "Third row" })).toHaveAttribute("aria-pressed", "true");
  await expect(question.getByRole("button", { name: "Two rows" })).toHaveAttribute("aria-pressed", "false");
  await cont(page, 1).click();
  await expect(page.locator('[data-service="Full Detail"]')).toContainText("$310");
  // Step 1 above: still there, and changing it changes the prices.
  await expect(question.getByRole("button", { name: "Third row" })).toHaveAttribute("aria-pressed", "true");
  await question.getByRole("button", { name: "Two rows" }).click();
  await expect(question.getByRole("button", { name: "Two rows" })).toHaveAttribute("aria-pressed", "true");
  await expect(question.getByRole("button", { name: "Third row" })).toHaveAttribute("aria-pressed", "false");
  await cont(page, 1).click();
  await expect(page.locator('[data-service="Full Detail"]')).toContainText("$280");
  await page.locator('[data-service="Exterior Only"]').click();
  await cont(page, 2).click();
  await expect(page.locator("#step-4")).toBeVisible();
  await address(page, "100 Example", "100 Example St NW");
  await cont(page, 4).click();
  await page.locator("[data-day]").first().click();
  await page.locator("[data-time]").first().click();
  await cont(page, 5).click();
  await details(page);
  await cont(page, 6).click();
  // Answered, so the summary shows it.
  await expect(page.locator("#step-7 .review-list")).toContainText("2020 Toyota Highlander · two rows");
});

test("the summary leaves out a size nobody was asked, as for a 2015 Honda Accord", async ({ page }) => {
  await pickVehicle(page, 2015, "Honda", "Accord");
  await expect(page.locator("[data-size-question]")).toHaveCount(0);
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await cont(page, 2).click();
  await page.locator('[data-level="3"]').click();
  await cont(page, 3).click();
  const card = page.locator("[data-request]");
  await expect(card.locator(".review-list")).toContainText("2015 Honda Accord");
  await expect(card.locator(".review-list")).not.toContainText("two rows");
});

test("the quote request card offers only the services for the vehicle: no Motorcycle Detail for a van or a car", async ({ page }) => {
  await pickVehicle(page, 2021, "Ford", "Transit 250");
  await cont(page, 1).click();
  const options = page.locator("#qr-service option");
  await expect(options).toHaveText(["Not sure", "Full Detail", "Interior Only", "Exterior Only", "1-Step Paint Correction", "2-Step Paint Correction"]);
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await cont(page, 2).click();
  await page.locator('[data-level="3"]').click();
  await cont(page, 3).click();
  await expect(options.filter({ hasText: "Motorcycle Detail" })).toHaveCount(0);
  await expect(options.filter({ hasText: "Full Detail" })).toHaveCount(1);
});

test("step 2 lists the add-ons Carpet, Seat, Headlight, and an add-on's price stays on one line on a phone @phone", async ({ page }) => {
  await pickVehicle(page, 2019, "Toyota", "RAV4");
  await cont(page, 1).click();
  await page.locator('[data-service="Full Detail"]').click();
  await expect(page.locator("#step-2 [data-add-on]")).toHaveCount(3);
  const names = await page.locator("#step-2 [data-add-on]").evaluateAll((boxes) => boxes.map((box) => box.dataset.addOn));
  expect(names).toEqual(["Carpet Extraction", "Seat Extraction", "Headlight Restoration"]);
  for (const price of await page.locator("#step-2 .add-on-price").all()) {
    await expect(price).toHaveText(/^\+ \$\d+$/);
    const lines = await price.evaluate((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight)));
    expect(lines).toBe(1);
  }
});

test("Turnstile is asked as the quote request card opens, and a check that times out once is retried on its own", async ({ page, request }) => {
  await page.clock.install();
  await page.goto("/book/");
  await page.evaluate(() => localStorage.setItem("fake-turnstile", "hang-once"));
  await pickVehicle(page, 2021, "Ford", "Transit 250");
  await cont(page, 1).click();
  await expect(page.getByRole("heading", { name: "Tell us about the job" })).toBeVisible();
  // Asked at once, before any photo is picked.
  await expect.poll(() => page.evaluate(() => window.fakeTurnstileChecks)).toBe(1);
  await page.setInputFiles("#qr-photos", twoPhotos);
  await expect(page.locator(".photo-tile .state", { hasText: "Uploading" })).toHaveCount(2);
  // The first check never answers; the retry does. Nothing is shown meanwhile.
  await page.clock.runFor(17000);
  await expect(page.locator(".photo-tile .state", { hasText: "Added" })).toHaveCount(2);
  await expect(page.locator("[data-request] .error")).toHaveText("");
  expect(await page.evaluate(() => window.fakeTurnstileChecks)).toBeGreaterThanOrEqual(2);
  await page.getByLabel("What do you need?").fill("Work van.");
  await address(page, "100 Example", "100 Example St NW");
  await page.getByLabel("First name").fill("Morgan");
  await page.getByLabel("Mobile number").pressSequentially("4235550160");
  await page.locator("[data-send-request]").click();
  await expect(page.getByRole("heading", { name: "Request sent" })).toBeVisible();
  const sent = (await log(request)).find((entry) => entry.to === "quote-requests");
  expect(sent.body.photos).toHaveLength(2);
});

test("a kept Turnstile token is replaced before it expires", async ({ page }) => {
  await page.clock.install();
  await pickVehicle(page, 2021, "Ford", "Transit 250");
  await cont(page, 1).click();
  await expect.poll(() => page.evaluate(() => window.fakeTurnstileChecks)).toBe(1);
  await page.clock.runFor(241000);
  expect(await page.evaluate(() => window.fakeTurnstileChecks)).toBe(2);
});

test("when Turnstile keeps failing, the photos stay with a plain message and can be tried again", async ({ page }) => {
  await page.clock.install();
  await page.goto("/book/");
  await page.evaluate(() => localStorage.setItem("fake-turnstile", "fail"));
  await pickVehicle(page, 2021, "Ford", "Transit 250");
  await cont(page, 1).click();
  await page.getByLabel("What do you need?").fill("Work van.");
  await page.setInputFiles("#qr-photos", twoPhotos);
  const error = page.locator("[data-request] .error");
  await page.clock.runFor(1000);
  await expect(error).toHaveText("");
  await page.clock.runFor(10000);
  await expect(error).toHaveText(`We couldn't get the photos ready to send just now. Try them again, or send the request without them and text the photos to ${PHONE}.`);
  await expect(error).not.toContainText("Turnstile");
  await expect(page.locator(".photo-tile")).toHaveCount(2);
  await expect(page.getByLabel("What do you need?")).toHaveValue("Work van.");
  await page.evaluate(() => localStorage.removeItem("fake-turnstile"));
  await page.locator("[data-photos-retry]").click();
  await page.clock.runFor(1000);
  await expect(page.locator(".photo-tile .state", { hasText: "Added" })).toHaveCount(2);
  await expect(error).toHaveText("");
});
