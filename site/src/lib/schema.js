// Structured data for search engines (schema.org JSON-LD), built from the
// data files and the published pricebook, so it always matches the page
// (website-and-seo.md, search ranking safeguards).

import { api, business, content, fillPrices, pages } from "./data.js";

const SITE = "https://dixiedetail.com";

export async function localBusiness() {
  const book = await api("services");
  const area = pages.service_area.counties.map((county) => ({ "@type": "AdministrativeArea", name: `${county.name}, Tennessee` }));
  const social = Object.values(business.social_profiles).filter(Boolean);
  const offers = book.services
    .filter((service) => service.from_price)
    .map((service) => ({
      "@type": "Offer",
      itemOffered: { "@type": "Service", name: service.name, description: service.description || undefined },
      priceSpecification: { "@type": "PriceSpecification", minPrice: service.from_price, priceCurrency: "USD" },
    }));
  return {
    "@context": "https://schema.org",
    "@type": "AutoWash",
    "@id": `${SITE}/#business`,
    name: business.trading_name,
    legalName: business.legal_name,
    url: SITE,
    telephone: "+1-" + business.phone.number.replace(/\D/g, "").replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3"),
    image: `${SITE}/social.jpg`,
    address: { "@type": "PostalAddress", postOfficeBoxNumber: "21", addressLocality: "Calhoun", addressRegion: "TN", postalCode: "37309", addressCountry: "US" },
    areaServed: area,
    sameAs: social,
    hasOfferCatalog: { "@type": "OfferCatalog", name: "Mobile detailing services", itemListElement: offers },
  };
}

export async function serviceSchema(service, pageUrl) {
  return {
    "@context": "https://schema.org",
    "@type": "Service",
    name: service.name,
    description: service.full,
    serviceType: "Mobile vehicle detailing",
    url: pageUrl,
    provider: { "@id": `${SITE}/#business` },
    areaServed: pages.service_area.counties.map((county) => `${county.name}, Tennessee`),
    offers: service.priced && service.priced.from_price
      ? { "@type": "Offer", priceSpecification: { "@type": "PriceSpecification", minPrice: service.priced.from_price, priceCurrency: "USD" } }
      : undefined,
  };
}

export async function faqSchema(items) {
  const filled = await Promise.all(items.map(async (item) => ({ question: item.question, answer: await fillPrices(item.answer) })));
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: filled.map((item) => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })),
  };
}

export { content };
