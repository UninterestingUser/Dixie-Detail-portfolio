"""Decode one upload, in a process of its own:

    python -m photoworker.decode UPLOAD JPEG

Reads UPLOAD, writes the clean JPEG to JPEG, and prints the result as one
line of JSON: {"width": W, "height": H}, or {"refused": CODE}. The worker
runs it with a time limit and kills it when the limit passes, so a photo
that hangs a decoder, or a crash inside one, refuses only that photo.
"""

import json
import os
import sys

from .imaging import Refused, clean


def main(upload, jpeg_path):
    with open(upload, "rb") as handle:
        data = handle.read()
    try:
        jpeg, width, height = clean(data)
    except Refused as refused:
        return {"refused": refused.code}
    partial = f"{jpeg_path}.part"
    with open(partial, "wb") as handle:
        handle.write(jpeg)
    os.replace(partial, jpeg_path)
    return {"width": width, "height": height}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2])))
