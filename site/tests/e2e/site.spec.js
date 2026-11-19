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
