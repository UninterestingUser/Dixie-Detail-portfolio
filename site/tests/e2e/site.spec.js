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
    const photo = page.locator(".page-top > img.page-top-photo");
    await expect(photo).toHaveAttribute("srcset", /page-header/);
    const box = await photo.boundingBox();
    const top = await page.locator(".page-top").boundingBox();
    expect(box.width).toBeCloseTo(page.viewportSize().width, -1);
    expect(box.height).toBeCloseTo(top.height - 6, 0);
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
  for (const path of ["/", "/cleveland-tn-mobile-detailing/"]) {
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
