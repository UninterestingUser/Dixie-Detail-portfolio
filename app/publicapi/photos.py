"""Quote request photos (decision 0099).

Each photo is opened as an image and refused if it is anything else, or has
an absurd pixel count. What is kept is a new JPEG, at most 2,560 pixels on
the long side, drawn into a fresh image so no metadata of any kind comes
along: no EXIF, no location, no camera, no color profile, no comments. The
original bytes are never written to disk. JPEG, PNG, WebP and HEIC (the
iPhone format, through pillow-heif) are accepted.

The files live in QUOTE_PHOTO_DIR under random names. No public endpoint
returns one; the control app shows them over Tailscale.
"""

import io
import os
import re
import secrets
import warnings

import pillow_heif
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

from .http import ApiError

pillow_heif.register_heif_opener()

# Formats as Pillow names them once it has opened the file.
FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}
LONG_SIDE = 2560
# A 48-megapixel phone photo is about 49 million pixels. Anything far past
# that is refused before it is decoded.
MAX_PIXELS = 64_000_000
JPEG_QUALITY = 85
FILE_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")


def max_bytes():
    return settings.QUOTE_REQUEST_PHOTO_MAX_MB * 1024 * 1024


def not_an_image():
    return ApiError(422, "not_an_image", "That file isn't a photo we can open. Send a JPEG, PNG, WebP or HEIC photo.")


def too_large():
    return ApiError(413, "photo_too_large", f"That photo is larger than {settings.QUOTE_REQUEST_PHOTO_MAX_MB} MB. Please send a smaller one.")


def clean_jpeg(data):
    """A new JPEG from the uploaded bytes, and its width and height."""
    if len(data) > max_bytes():
        raise too_large()
    with warnings.catch_warnings():
        # A decompression bomb is refused, never decoded.
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(io.BytesIO(data))
            if image.format not in FORMATS:
                raise not_an_image()
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise ApiError(422, "not_an_image", "That photo's size isn't one we can use. Please send an ordinary photo.")
            if image.format == "JPEG":
                # Decode a large JPEG at a reduced scale, still at least the
                # final size: far less memory for a phone's 48-megapixel photo.
                image.draft("RGB", (LONG_SIDE, LONG_SIDE))
            image.load()
            image = ImageOps.exif_transpose(image)
        except ApiError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError, SyntaxError, EOFError) as error:
            raise not_an_image() from error
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, "white")
        flat.paste(rgba, mask=rgba.getchannel("A"))
    else:
        flat = image.convert("RGB")
    flat.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
    # A fresh image holds the pixels only: nothing from image.info comes along.
    clean = Image.new("RGB", flat.size)
    clean.paste(flat)
    out = io.BytesIO()
    clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue(), clean.width, clean.height


def folder():
    path = settings.QUOTE_PHOTO_DIR
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def path_of(name):
    if not FILE_NAME.match(name or ""):
        raise ValueError("Not a photo file name.")
    return settings.QUOTE_PHOTO_DIR / name


def store(jpeg):
    """Write the JPEG under a new random name, readable by the app only."""
    name = f"{secrets.token_hex(16)}.jpg"
    final = folder() / name
    partial = final.with_suffix(".part")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(jpeg)
    os.replace(partial, final)
    return name


def delete_file(name):
    try:
        path_of(name).unlink(missing_ok=True)
    except ValueError:
        pass


def delete_photos(photos):
    """Delete the photos' files, then their records. Returns how many."""
    photos = list(photos)
    for photo in photos:
        delete_file(photo.file_name)
    for photo in photos:
        photo.delete()
    return len(photos)
