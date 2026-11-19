// The website's pages outside the booking flow: the homepage's cards and
// hero, the one services page and the old addresses that redirect to it
// (acceptance changes B, 2026-11-18; docs/reference/website-and-seo.md).
import { expect, test } from "@playwright/test";

const CARDS = [
  ["Premium Detailing", "See my price", "/services/#detail"],
  ["Paint Correction", "See my price", "/services/#correction"],
  ["Headlight Restoration", "Add to detail", "/services/#headlight"],
  ["Shampoo & Extraction", "Add to detail", "/services/#extraction"],
];

test("the homepage has four service cards, 2 x 2, with a from price and two buttons", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  const cards = page.locator(".service-card");
  await expect(cards.locator("h3")).toHaveText(CARDS.map(([title]) => title));
  await expect(page.locator(".service-card", { hasText: "Motorcycle" })).toHaveCount(0);
  for (const [index, [title, first, info]] of CARDS.entries()) {
    const card = cards.nth(index);
    await expect(card.locator(".price-box")).toHaveText(/^from \$\d+$/);
    await expect(card.locator(".card-buttons a")).toHaveText([first, "More info"]);
    await expect(card.locator(".card-buttons a").first()).toHaveAttribute("href", "/book/");
    await expect(card.locator(".card-buttons a").last()).toHaveAttribute("href", info);
    // Side by side on a wide screen.
    const [a, b] = await Promise.all([card.locator(".card-buttons a").first().boundingBox(), card.locator(".card-buttons a").last().boundingBox()]);
    expect(Math.abs(a.y - b.y), title).toBeLessThan(2);
  }
  const [one, two, three] = await Promise.all([0, 1, 2].map((i) => cards.nth(i).boundingBox()));
  expect(Math.abs(one.y - two.y)).toBeLessThan(2);
  expect(three.y).toBeGreaterThan(one.y + one.height);
  // The lowest car and truck price: Exterior Only on a Small car in the fake price book.
  await expect(cards.nth(0).locator(".price-box")).toHaveText("from $110");
});

test("the hero box reads \"See your exact price\", and its button matches the dropdowns", async ({ page }) => {
  for (const width of [1920, 412]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.locator(".picker-title")).toHaveText("See your exact price");
    const button = page.locator(".picker button[type=submit]");
    await expect(button).toHaveText("See Price");
    const [select, box] = await Promise.all([page.locator("#hero-year").boundingBox(), button.boundingBox()]);
    expect(Math.round(box.height), `width ${width}`).toBe(Math.round(select.height));
    // One line: no taller than the dropdown.
    expect(await button.evaluate((el) => el.scrollHeight <= el.clientHeight + 1)).toBe(true);
  }
});

test("the questions box keeps \"Call or text\" on one line", async ({ page }) => {
  for (const width of [1920, 412]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const call = page.locator(".cta a", { hasText: "Call or text" });
    const height = await call.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight) || 20);
    const box = await call.boundingBox();
    expect(box.height, `width ${width}`).toBeLessThanOrEqual(60);
    expect(await call.evaluate((el) => el.scrollWidth <= el.clientWidth + 1), `width ${width}`).toBe(true);
    expect(height).toBeGreaterThan(0);
  }
});

test("on a phone, the opened menu sits on top of the page on the accent blue", async ({ page }) => {
  await page.setViewportSize({ width: 412, height: 915 });
  await page.goto("/");
  await page.locator(".menu > summary").click();
  const menu = page.locator(".menu nav");
  await expect(menu).toBeVisible();
  expect(await menu.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(0, 45, 101)");
  // The link at the menu's middle is what a tap there reaches, not the hero text under it.
  const box = await menu.getByRole("link", { name: "Contact" }).boundingBox();
  const hit = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.textContent, [box.x + box.width / 2, box.y + box.height / 2]);
  expect(hit).toBe("Contact");
});

test("the services page has four anchored sections with their red boxes and no price tables", async ({ page }) => {
  await page.goto("/services/");
  for (const [anchor, title, button] of [["detail", "Premium Detailing", "See my price"], ["correction", "Paint Correction", "See my price"], ["headlight", "Headlight Restoration", "Add to detail"], ["extraction", "Shampoo & Extraction", "Add to detail"]]) {
    const section = page.locator(`section#${anchor}`);
    await expect(section.locator("h2").first()).toHaveText(title);
    await expect(section.locator("img")).toHaveCount(1);
    await expect(section.locator(".cta .button").first()).toHaveText(button);
  }
  await expect(page.locator("section#detail")).toContainText("Motorcycle Detail");
  await expect(page.locator("table")).toHaveCount(0);
});

for (const [old, anchor] of [["detailing", "detail"], ["paint-correction", "correction"], ["headlight-restoration", "headlight"], ["shampoo-and-extraction", "extraction"], ["motorcycle-detail", "detail"]]) {
  test(`/services/${old}/ redirects permanently to /services/#${anchor}`, async ({ request, page }) => {
    const answer = await request.get(`/services/${old}/`, { maxRedirects: 0 });
    expect(answer.status()).toBe(301);
    expect(answer.headers().location).toBe(`/services/#${anchor}`);
    await page.goto(`/services/${old}/`);
    await expect(page).toHaveURL(new RegExp(`/services/#${anchor}$`));
  });
}

// Acceptance changes 2 (owner, 2026-11-18) -----------------------------------

test("every page but the homepage has the header photo, under a 50% shade, down to the red line", async ({ page }) => {
  for (const path of ["/services/", "/about/", "/contact/", "/reviews/", "/faq/", "/book/", "/privacy-policy/", "/cleveland-tn-mobile-detailing/"]) {
    await page.goto(path);
    const photo = page.locator(".page-top > .page-top-photo > img");
    await expect(photo).toHaveAttribute("srcset", /page-header/);
    const box = await photo.boundingBox();
    const top = await page.locator(".page-top").boundingBox();
    expect(box.width).toBeCloseTo(page.viewportSize().width, -1);
    // Twice the header's height, so the photo's middle row, the bottom of
    // the nearest car's headlights, sits on the red line; the box clips it.
    expect(box.y).toBeCloseTo(top.y, 0);
    expect(box.height).toBeCloseTo(2 * (top.height - 6), 0);
    const clip = await page.locator(".page-top-photo").boundingBox();
    expect(clip.height).toBeCloseTo(top.height - 6, 0);
    expect(await page.locator(".page-top").evaluate((el) => getComputedStyle(el, "::after").backgroundColor)).toBe("rgba(0, 0, 0, 0.5)");
  }
  await page.goto("/");
  await expect(page.locator(".page-top")).toHaveCount(0);
});

test("the homepage: \"Restore the shine\", no buttons under it, each step two lines, and the services subhead", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator("#how h2")).toHaveText("Restore the shine");
  await expect(page.locator("#how .button")).toHaveCount(0);
  const lines = await page.locator(".steps span.text").evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight))));
  expect(lines).toEqual([2, 2, 2]);
  await expect(page.locator("#services .lead")).toHaveText("We provide upfront pricing right here on our website. Pick your vehicle, see the exact price with tax, and pick a day that works for you. We show up and handle the rest.");
});

test("on a desktop each service card's photo is a full-height square on the right, with the text left of it", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  for (const path of ["/", "/cleveland-tn-mobile-detailing/", "/athens-tn-mobile-detailing/", "/chattanooga-tn-mobile-detailing/"]) {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    for (const card of await page.locator(".service-card").all()) {
      const c = await card.boundingBox();
      const p = await card.locator(".service-card-photo img").boundingBox();
      const t = await card.locator(".text").boundingBox();
      expect(Math.abs(p.width - p.height)).toBeLessThanOrEqual(1);
      expect(Math.abs(p.height - c.height)).toBeLessThanOrEqual(1);
      expect(Math.abs(p.x + p.width - (c.x + c.width))).toBeLessThanOrEqual(1);
      expect(t.x + t.width).toBeLessThanOrEqual(p.x);
    }
  }
});

test("on a phone each service card's photo sits at the top @phone", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone only");
  await page.goto("/");
  for (const card of await page.locator(".service-card").all()) {
    const c = await card.boundingBox();
    const p = await card.locator(".service-card-photo img").boundingBox();
    expect(Math.abs(p.y - c.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(p.width - c.width)).toBeLessThanOrEqual(1);
  }
});

test("the services, about and contact page tops and the red box headings use the owner's words", async ({ page }) => {
  await page.goto("/services/");
  await expect(page.locator(".page-head .eyebrow")).toHaveCount(0);
  await expect(page.locator(".page-head h1")).toHaveText("Mobile Detailing Services");
  await expect(page.locator(".page-head .lead")).toHaveText("We come to your driveway in Bradley, McMinn, Hamilton, Polk, and Meigs Counties.");
  for (const [anchor, heading] of [["detail", "Book your detail today"], ["correction", "Book a paint correction"], ["headlight", "Restore your headlights"], ["extraction", "Book your detail today"]]) {
    await expect(page.locator(`#${anchor} .cta h2`)).toHaveText(heading);
  }
  await page.goto("/about/");
  await expect(page.locator(".page-head .eyebrow")).toHaveCount(0);
  await expect(page.locator(".page-head h1")).toHaveText("About Dixie Detail");
  await expect(page.locator(".page-head .lead")).toHaveText("An eye for perfection and a passion for quality");
  await page.goto("/contact/");
  await expect(page.locator(".page-head .lead")).toHaveText("Have a question or comment? Call or text us and we'll get back to you right away.");
});

// Acceptance changes 3 (owner, 2026-11-19) -----------------------------------

const CITIES = [
  ["/cleveland-tn-mobile-detailing/", "Mobile detailing in Cleveland TN", "We'll come to your driveway anywhere in Bradley County."],
  ["/athens-tn-mobile-detailing/", "Mobile detailing in Athens TN", "We'll come to your driveway anywhere in McMinn County."],
  ["/chattanooga-tn-mobile-detailing/", "Mobile detailing in Chattanooga TN", "We'll come to your driveway anywhere in Hamilton County."],
];

const CARD_TEXT = [
  "A full-service cleaning that meticulously reaches every corner of your car, inside and out. This isn't just a quick vacuum and wipe down. It's a complete restoration and you get a new car again.",
  "Decontamination plus a machine polish to remove imperfections, finished with ceramic wax that protects for up to a year. This goes beyond the detailed cleaning to restore the glossy finish.",
  "Multi-stage removal of the UV-damaged outer layer followed by a polish and buff to restore clarity. We finish by adding UV protection to ensure they don't turn hazy again in a month.",
  "For carpets and cloth seats that need a deeper cleaning. Add this to any interior detail service to pull out smells and filth that have embedded deep into the seats or carpet.",
];

// Answers any call to Google Maps from the test, so nothing leaves the machine.
async function fakeGoogleMaps(page) {
  const asked = [];
  await page.route("https://www.google.com/maps/**", (route) => {
    asked.push(route.request().url());
    return route.fulfill({ contentType: "text/html", body: "<!doctype html><title>map</title>" });
  });
  return asked;
}

test("the homepage's cards carry the owner's text, and the city pages show the same cards", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".service-card .text")).toHaveText(CARD_TEXT);
  const home = await page.locator(".service-card").evaluateAll((cards) => cards.map((card) => card.innerText));
  for (const [path, heading, lead] of CITIES) {
    await page.goto(path);
    expect(await page.locator(".service-card").evaluateAll((cards) => cards.map((card) => card.innerText))).toEqual(home);
    await expect(page.locator(".page-head .eyebrow")).toHaveCount(0);
    await expect(page.locator(".page-head h1")).toHaveText(heading);
    await expect(page.locator(".page-head .lead")).toHaveText(lead);
  }
  await page.goto(CITIES[0][0]);
  await expect(page.locator("main .split .lead").first()).toHaveText("Downtown Cleveland, north Cleveland and the Paul Huff / Bradley Square area, the Lee University and Ocoee Street neighborhoods, south Cleveland, Charleston, Georgetown, McDonald, Waterlevel Hwy, Dalton Pike, and the rest of Bradley County. If your driveway has a Bradley County address, Dixie Detail has you covered.");
});

test("the homepage menu's backing is 10% darker, with the buttons' corners", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  const nav = page.locator(".site-header .nav");
  expect(await nav.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgba(20, 21, 24, 0.72)");
  const [backing, button] = await Promise.all([nav.evaluate((el) => getComputedStyle(el).borderRadius), nav.locator(".button").evaluate((el) => getComputedStyle(el).borderRadius)]);
  expect(backing).toBe(button);
  expect(await nav.evaluate((el) => getComputedStyle(el).padding)).toBe("6px 6px 6px 26px");
});

test("the homepage's sections: reviews after services, then the service area, then the six questions", async ({ page }) => {
  await page.goto("/");
  const order = await page.locator("#services, #reviews, #area, #faq").evaluateAll((els) => els.map((el) => el.id));
  expect(order).toEqual(["services", "reviews", "area", "faq"]);
  await expect(page.locator("#faq summary")).toHaveText([
    "Is there a Dixie Detail shop where I can drop off my car?",
    "What do you need from me on the day of the appointment?",
    "I have stuff in my car. Does it need to be empty before you arrive?",
    "Do the glove box and center console need to be empty?",
    "I have a situation that goes beyond a normal detail. How do I book that?",
    "How much are your services?",
  ]);
  // The prices come from the pricebook: the fake's, not the owner's typed ones.
  await page.locator("#faq summary").last().click();
  await expect(page.locator("#faq details").last().locator("p")).toHaveText(/^A Full Detail starts at \$\d+, depending on the vehicle's size\. Paint correction starts at \$\d+\. Headlight restoration is \$\d+ for both lights\. Carpet and seat extraction are add-ons from \$\d+\./);
  // All six are on /faq/ too.
  await page.goto("/faq/");
  const all = await page.locator("summary").allTextContents();
  expect(new Set(all).size).toBe(all.length);
  for (const question of ["Is there a Dixie Detail shop where I can drop off my car?", "How much are your services?", "I have a situation that goes beyond a normal detail. How do I book that?"]) expect(all).toContain(question);
});

test("the service area: counties under the heading, the city buttons over the map, and the map loads only on approach", async ({ page }) => {
  const asked = await fakeGoogleMaps(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  const area = page.locator("#area");
  await expect(area.locator(".lead")).toHaveCount(0);
  await expect(area.locator(".area-cities a")).toHaveText(["Cleveland", "Athens", "Chattanooga"]);
  await expect(area.locator(".area-cities a").first()).toHaveClass(/button/);
  // Nothing from Google on the first screen.
  await page.waitForLoadState("networkidle");
  expect(asked).toEqual([]);
  await expect(area.locator("iframe")).toHaveCount(0);
  await area.scrollIntoViewIfNeeded();
  const frame = area.locator("iframe");
  await expect(frame).toHaveAttribute("title", "Map of the Dixie Detail service area around Cleveland, Tennessee");
  const src = new URL(await frame.getAttribute("src"));
  expect(src.origin + src.pathname).toBe("https://www.google.com/maps/embed/v1/view");
  expect(src.searchParams.get("center")).toBe("35.1595,-84.8766");
  expect(src.searchParams.get("zoom")).toBe("9");
  expect(src.searchParams.get("q")).toBeNull();
  expect(src.searchParams.get("key")).toBeTruthy();
  await expect.poll(() => asked.length).toBe(1);
  // The counties under the heading, the map to their right, the buttons just above the map.
  const [heading, counties, buttons, map] = await Promise.all(["h2", ".counties", ".area-cities", ".map"].map((s) => area.locator(s).boundingBox()));
  expect(counties.y).toBeGreaterThan(heading.y);
  expect(map.x).toBeGreaterThan(counties.x + counties.width);
  expect(buttons.y + buttons.height).toBeLessThanOrEqual(map.y);
  expect(map.y - (buttons.y + buttons.height)).toBeLessThan(24);
});

test("on a phone the service area stacks the counties, the buttons and the map @phone", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone only");
  await fakeGoogleMaps(page);
  await page.goto("/");
  const area = page.locator("#area");
  const [counties, buttons, map] = await Promise.all([".counties", ".area-cities", ".map"].map((s) => area.locator(s).boundingBox()));
  expect(buttons.y).toBeGreaterThan(counties.y + counties.height);
  expect(map.y).toBeGreaterThan(buttons.y + buttons.height);
  expect(map.width).toBeCloseTo(counties.width, 0);
});

test("reviews come from the API: name, text and stars when given, the Google link, no combined rating", async ({ page }) => {
  await page.goto("/");
  const reviews = page.locator("#reviews [data-review]");
  await expect(reviews).toHaveCount(3);
  await expect(reviews.locator("figcaption strong")).toHaveText(["Alex T.", "Sam R.", "Jo M."]);
  await expect(reviews.first().locator("blockquote")).toHaveText("“Invented review one. The truck looks new again.”");
  await expect(reviews.nth(0).locator(".stars")).toHaveAttribute("aria-label", "5 out of 5 stars");
  await expect(reviews.nth(1).locator(".stars")).toHaveCount(0);
  await expect(reviews.nth(2).locator(".stars")).toHaveAttribute("aria-label", "4 out of 5 stars");
  await expect(reviews.nth(0).locator("figcaption a")).toHaveAttribute("href", "https://g.co/kgs/example-1");
  await expect(page.locator("#reviews").getByRole("link", { name: "Google", exact: true })).toBeVisible();
  await expect(page.locator("#reviews")).not.toContainText(/average|out of 5 from|\d\.\d stars/i);
  await expect(page.locator("#reviews img.backdrop")).toHaveCount(1);

  await page.goto("/reviews/");
  await expect(page.locator("[data-review]")).toHaveCount(4);
  // The plain white page, with no car photo behind it.
  await expect(page.locator("#reviews img.backdrop")).toHaveCount(0);
  expect(await page.locator("#reviews").evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(255, 255, 255)");
});

test("the privacy policy says the map may set Google's cookies", async ({ page }) => {
  await page.goto("/privacy-policy/");
  await expect(page.getByText("The service area map on our homepage is embedded from Google Maps, which may set its own cookies.", { exact: false })).toBeVisible();
});
