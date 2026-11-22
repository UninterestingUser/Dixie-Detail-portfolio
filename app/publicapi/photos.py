"""Quote request photos (decisions 0099, 0120 and 0123).

The public service never decodes a photo itself. It writes the upload to
the photo worker's inbox, a tmpfs volume, and waits for the worker's
result: a clean JPEG with no metadata, made in a container with no network,
no secrets and no database (photoworker). Where no inbox is set
(PHOTO_INBOX_DIR empty: development and tests), the same decode runs here,
in a fresh process with the same time limit. Either way the original bytes
are never written to disk, and a photo that fails or takes too long to
decode is refused as not_an_image. The decode rules are in
photoworker.imaging.

The files live in QUOTE_PHOTO_DIR under random names. No public endpoint
returns one; the control app shows them over Tailscale.
"""

import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

from django.conf import settings

from photoworker import worker
from photoworker.imaging import FORMATS, OPENED_AS  # noqa: F401 (the accepted formats, for tests and readers)

from .http import ApiError

FILE_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")


def max_bytes():
    return settings.QUOTE_REQUEST_PHOTO_MAX_MB * 1024 * 1024


def not_an_image():
    return ApiError(422, "not_an_image", "That file isn't a photo we can open. Send a JPEG, PNG, WebP or HEIC photo.")


def too_large():
    return ApiError(413, "photo_too_large", f"That photo is larger than {settings.QUOTE_REQUEST_PHOTO_MAX_MB} MB. Please send a smaller one.")


def bad_size():
    return ApiError(422, "not_an_image", "That photo's size isn't one we can use. Please send an ordinary photo.")


def write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def through_worker(data, ident):
    """Hand the upload to the photo worker and wait for its result."""
    inbox, outbox = Path(settings.PHOTO_INBOX_DIR), Path(settings.PHOTO_OUTBOX_DIR)
    partial = inbox / f"{ident}.part"
    write_private(partial, data)
    # The worker takes only *.upload names, so it never sees a half-written file.
    os.replace(partial, inbox / f"{ident}.upload")
    result_path, jpeg_path = outbox / f"{ident}.json", outbox / f"{ident}.jpg"
    deadline = time.monotonic() + settings.PHOTO_DECODE_WAIT_SECONDS
    try:
        while not result_path.exists():
            if time.monotonic() > deadline:
                # The worker is down or far behind: refused, as a failed decode is.
                return {"refused": "not_an_image"}, None
            time.sleep(0.05)
        result = json.loads(result_path.read_text())
        jpeg = jpeg_path.read_bytes() if "refused" not in result else None
        return result, jpeg
    finally:
        for leftover in (inbox / f"{ident}.upload", result_path, jpeg_path):
            leftover.unlink(missing_ok=True)


def here(data, ident):
    """The same decode, in this container (development and tests)."""
    shm = "/dev/shm" if os.path.isdir("/dev/shm") else None
    with tempfile.TemporaryDirectory(dir=shm) as box:
        write_private(Path(box) / f"{ident}.upload", data)
        result = worker.run_one(box, box, ident, settings.PHOTO_DECODE_SECONDS)
        jpeg_path = Path(box) / f"{ident}.jpg"
        return result, (jpeg_path.read_bytes() if "refused" not in result else None)


def clean_jpeg(data):
    """A new JPEG from the uploaded bytes, and its width and height."""
    if len(data) > max_bytes():
        raise too_large()
    ident = secrets.token_hex(16)
    result, jpeg = (through_worker if settings.PHOTO_INBOX_DIR else here)(data, ident)
    if result.get("refused") == "bad_size":
        raise bad_size()
    if "refused" in result or not jpeg:
        raise not_an_image()
    return jpeg, result["width"], result["height"]


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
