// Build-time data: the repository's data files and the public API.
//
// Prices, services, classes, condition levels, the consent wording and the
// price table come from the public API when the site is built
// (docs/reference/website-and-seo.md), so every page shows the pricebook in
// effect. If the API can't be reached the build fails, and Cloudflare keeps
// serving the last good build: the site never goes out without prices.
// Text comes from data/site-content.yaml (the owner's words) and
// data/site-pages.yaml (carried over from the old site).

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { parse } from "yaml";
import { setting } from "./settings.js";

const here = path.dirname(fileURLToPath(import.meta.url));
// site/src/lib -> the repository's data/ folder.
export const DATA_DIR = process.env.DIXIE_DATA_DIR || path.resolve(here, "../../../data");

export const API_BASE = setting("API_BASE").replace(/\/+$/, "");

export function readData(name) {
  return parse(readFileSync(path.join(DATA_DIR, name), "utf8"));
}

export function readOptionalData(name) {
  const file = path.join(DATA_DIR, name);
  return existsSync(file) ? parse(readFileSync(file, "utf8")) : null;
}

const cache = new Map();

async function fetchJson(endpoint) {
  const url = `${API_BASE}/${endpoint}`;
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(url, { headers: { Accept: "application/json", "User-Agent": "dixie-detail-site-build" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, attempt * 1000));
    }
  }
  throw new Error(`The site build could not read ${url}: ${lastError.message}. The last good build stays live.`);
}

export function api(endpoint) {
  if (!cache.has(endpoint)) cache.set(endpoint, fetchJson(endpoint));
  return cache.get(endpoint);
}

export const content = readData("site-content.yaml");
export const pages = readData("site-pages.yaml");
export const business = readData("business.yaml");
// Real reviews the owner supplies; never written for the site. The file is
// optional, and without it the reviews section links to Google only.
export const reviews = (readOptionalData("reviews.yaml") || {}).reviews || [];

export const phone = business.phone;

// The services in the order site-content.yaml lists them, each with its
// pricebook entry (id, from price, price cells), when the pricebook has it.
export async function servicesWithPrices() {
  const book = await api("services");
  const byName = new Map(book.services.map((service) => [service.name, service]));
  return content.services
    .map((text) => ({ ...text, priced: byName.get(text.name) || null }))
    .filter((service) => service.priced);
}

// "$200" from "200.00": the server's amount, shown without its cents when
// it has none. Never arithmetic (decision 0059).
export function dollars(amount) {
  if (amount == null) return "";
  return "$" + String(amount).replace(/\.00$/, "");
}

// Fill {from:Service} and {price:Service} tokens in carried-over text.
export async function fillPrices(text) {
  const book = await api("services");
  const byName = new Map(book.services.map((service) => [service.name, service]));
  return text.replace(/\{(from|price):([^}]+)\}/g, (match, kind, name) => {
    const service = byName.get(name.trim());
    if (!service || !service.from_price) throw new Error(`No price for "${name}" in the pricebook (site-pages.yaml).`);
    return dollars(service.from_price);
  });
}

// The four service sections in data/site-content.yaml, each with its
// services (text and pricebook entry) and its "from" price: the lowest of
// the pricebook's own prices for its price_from services, cars and trucks
// only. A comparison, never arithmetic (decision 0059).
export async function serviceSections() {
  const priced = await servicesWithPrices();
  return content.sections.map((section) => {
    const cells = priced.filter((service) => section.price_from.includes(service.name)).flatMap((service) => service.priced.prices);
    const from = cells.map((cell) => cell.price).sort((a, b) => Number(a) - Number(b))[0] || null;
    return { ...section, from, services: section.services.map((name) => priced.find((service) => service.name === name)).filter(Boolean) };
  });
}
