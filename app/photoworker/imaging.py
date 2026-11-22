"""Turning an uploaded photo into a clean JPEG (decisions 0099 and 0120).

Each photo is opened as an image and refused if it is anything else, or has
an absurd pixel count. What is kept is a new JPEG, at most 2,560 pixels on
the long side, drawn into a fresh image so no metadata of any kind comes
along: no EXIF, no location, no camera, no color profile, no comments.
JPEG, PNG, WebP and HEIC (the iPhone format, through pillow-heif) are
accepted. No Django here: this runs in the photo worker.
"""

import io
import warnings

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()

# Formats as Pillow names them. Only these decoders ever see an upload:
# Image.open tries no other, so a file in any other format (TIFF, GIF, PDF,
# EPS and the rest, where most of Pillow's security bugs have been) is
# refused before any of its bytes are parsed (decision 0120).
FORMATS = ("JPEG", "PNG", "WEBP", "HEIF")
# A JPEG holding more than one picture, as some Android phones and cameras
# write, opens through the JPEG decoder as "MPO". Only its first picture, the
# photo itself, is read: nothing here seeks to the others.
OPENED_AS = {*FORMATS, "MPO"}
LONG_SIDE = 2560
# A 48-megapixel phone photo is about 49 million pixels. Anything far past
# that is refused before it is decoded.
MAX_PIXELS = 64_000_000
JPEG_QUALITY = 85


class Refused(Exception):
    """The upload isn't a photo this can use. code is "not_an_image" or
    "bad_size"; the public API words the answer."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def clean(data):
    """A new JPEG from the uploaded bytes, and its width and height."""
    with warnings.catch_warnings():
        # A decompression bomb is refused, never decoded.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(io.BytesIO(data), formats=FORMATS)
            if image.format not in OPENED_AS:
                raise Refused("not_an_image")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise Refused("bad_size")
            if image.format in ("JPEG", "MPO"):
                # Decode a large JPEG at a reduced scale, still at least the
                # final size: far less memory for a phone's 48-megapixel photo.
                image.draft("RGB", (LONG_SIDE, LONG_SIDE))
            image.load()
            image = ImageOps.exif_transpose(image)
        except Refused:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError, EOFError) as error:
            raise Refused("not_an_image") from error
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")
        flat.paste(rgba, mask=rgba.getchannel("A"))
    else:
        flat = image.convert("RGB")
    flat.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
    # A fresh image holds the pixels only: nothing from image.info comes along.
    clean_image = Image.new("RGB", flat.size)
    clean_image.paste(flat)
    out = io.BytesIO()
    clean_image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue(), clean_image.width, clean_image.height
