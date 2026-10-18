"""Values every control app page needs."""

from functools import lru_cache

import yaml
from django.conf import settings


@lru_cache
def brand_colors():
    """The brand colors from data/business.yaml, the one place they are kept."""
    brand = yaml.safe_load((settings.DATA_DIR / "business.yaml").read_text())["brand"]
    return {
        "red": brand["primary_red"],
        "navy": brand["accent_navy"],
        "white": brand["white"],
        "charcoal": brand["footer_charcoal"],
    }


def brand(request):
    return {"brand": brand_colors()}
