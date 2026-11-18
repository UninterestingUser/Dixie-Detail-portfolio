#!/usr/bin/env python3
"""Make the trimmed Archivo font the website serves.

Reads site/src/assets/fonts/archivo.json, which names the source font from
the @fontsource-variable/archivo package, the weight and width ranges the
site uses and the characters it shows, and writes
site/src/assets/fonts/archivo.woff2 with only those: about half the size of
the full font, which keeps the homepage's largest paint well under its
target (docs/reference/website-and-seo.md). Archivo is under the SIL Open
Font License, which allows this, with no reserved font name.

Run it after changing archivo.json or updating the font package, from the
repository root, with the site's packages installed (cd site && npm ci).
Needs fontTools and Brotli (on Fedora: sudo dnf install python3-fonttools
python3-brotli).

  python3 tools/make_site_font.py
"""

import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

REPO = Path(__file__).resolve().parent.parent
FONTS = REPO / "site/src/assets/fonts"


def main():
    spec = json.loads((FONTS / "archivo.json").read_text())
    font = TTFont(REPO / "site" / spec["source"])
    font = instancer.instantiateVariableFont(
        font, {"wght": tuple(spec["weight"]), "wdth": tuple(spec["width"])}, updateFontNames=False
    )
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["kern", "liga", "calt"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=subset.parse_unicodes(",".join(spec["unicodes"])))
    subsetter.subset(font)
    out = FONTS / "archivo.woff2"
    font.flavor = "woff2"
    font.save(out)
    print(f"Wrote {out.relative_to(REPO)}: {out.stat().st_size:,} bytes.")


if __name__ == "__main__":
    main()
