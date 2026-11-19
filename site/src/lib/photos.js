// The section photos (site-content.yaml, section_images), by section anchor:
// on the services page and, square, on the homepage service cards.
import { content } from "./data.js";

const photos = import.meta.glob("../assets/page-photos/*.webp", { eager: true });

export function sectionPhoto(anchor) {
  const file = content.section_images[anchor];
  return Object.entries(photos).find(([key]) => key.endsWith("/" + file))?.[1]?.default;
}
