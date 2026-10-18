#!/usr/bin/env python3
"""Draw the control app's home-screen icons in the brand colors.

Writes app/control/static/control/icons/icon-192.png and icon-512.png: white
"DD" on the brand red, full bleed, with the letters inside the middle 60% so
Android can crop the icon to any shape (a "maskable" icon). Run it again after
the brand colors in data/business.yaml change.

Needs Pillow and PyYAML (on Fedora: sudo dnf install python3-pillow
python3-pyyaml) and the Liberation Sans font (liberation-sans-fonts).

  python3 tools/make_app_icons.py
"""

from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "app/control/static/control/icons"
FONT = "/usr/share/fonts/liberation-sans-fonts/LiberationSans-BoldItalic.ttf"


def draw(size, background, letters):
    image = Image.new("RGB", (size, size), background)
    canvas = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, round(size * 0.36))
    left, top, right, bottom = canvas.textbbox((0, 0), "DD", font=font)
    x = (size - (right - left)) / 2 - left
    y = (size - (bottom - top)) / 2 - top
    canvas.text((x, y), "DD", font=font, fill=letters)
    return image


def main():
    brand = yaml.safe_load((REPO / "data/business.yaml").read_text())["brand"]
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw(size, brand["primary_red"], brand["white"]).save(OUT / f"icon-{size}.png", optimize=True)
        print(f"wrote {OUT / f'icon-{size}.png'}")


if __name__ == "__main__":
    main()
