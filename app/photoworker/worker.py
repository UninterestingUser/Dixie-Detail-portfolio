"""The photo worker's loop (decision 0123).

The public service writes each upload to the inbox, a tmpfs volume shared
with this container only, as ID.upload. The worker takes them one at a time,
oldest first, and decodes each in a fresh process (photoworker.decode) with
a time limit. It writes the clean JPEG to the outbox as ID.jpg and then the
result as ID.json, last, so the result's presence means the photo is done,
and deletes the upload either way. A decode that fails, crashes or runs out
of time is a refused photo: {"refused": "not_an_image"}.

Settings, from the environment: PHOTO_INBOX_DIR, PHOTO_OUTBOX_DIR and
PHOTO_DECODE_SECONDS (the time limit, 20 by default). The worker logs only
counts and timings, never a file's content.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

UPLOAD = re.compile(r"^([0-9a-f]{32})\.upload$")
DECODE_COMMAND = [sys.executable, "-m", "photoworker.decode"]
# The folder that holds this package, so the child finds it from anywhere.
APP_DIR = Path(__file__).resolve().parent.parent
HEARTBEAT = Path("/tmp/photo-worker-alive")


def write_json(path, value):
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(value))
    os.replace(partial, path)


def decode(upload, jpeg, seconds):
    """The decode's result as a dict; refused when it fails or times out."""
    try:
        done = subprocess.run([*DECODE_COMMAND, str(upload), str(jpeg)], capture_output=True, timeout=seconds, check=False, cwd=APP_DIR)
    except subprocess.TimeoutExpired:
        return {"refused": "not_an_image", "reason": f"timed out after {seconds:g}s"}
    if done.returncode != 0:
        return {"refused": "not_an_image", "reason": f"the decoder exited {done.returncode}"}
    try:
        result = json.loads(done.stdout.decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"refused": "not_an_image", "reason": "the decoder gave no result"}
    if "refused" not in result and not jpeg.exists():
        return {"refused": "not_an_image", "reason": "the decoder wrote no photo"}
    return result


def run_one(inbox, outbox, ident, seconds):
    """Decode inbox/ID.upload into outbox/ID.jpg and outbox/ID.json."""
    upload = Path(inbox) / f"{ident}.upload"
    jpeg = Path(outbox) / f"{ident}.jpg"
    started = time.monotonic()
    try:
        result = decode(upload, jpeg, seconds)
    finally:
        upload.unlink(missing_ok=True)
        Path(f"{jpeg}.part").unlink(missing_ok=True)
    if "refused" in result:
        jpeg.unlink(missing_ok=True)
    write_json(Path(outbox) / f"{ident}.json", {key: value for key, value in result.items() if key != "reason"})
    outcome = f"refused ({result['reason']})" if "reason" in result else ("refused" if "refused" in result else "decoded")
    print(f"photo-worker: {outcome} in {time.monotonic() - started:.1f}s", flush=True)
    return result


def waiting(inbox):
    """The IDs waiting in the inbox, oldest first."""
    found = []
    for entry in os.scandir(inbox):
        match = UPLOAD.match(entry.name)
        if match:
            try:
                found.append((entry.stat().st_mtime, match.group(1)))
            except FileNotFoundError:
                continue
    return [ident for _, ident in sorted(found)]


def main():
    inbox = os.environ["PHOTO_INBOX_DIR"]
    outbox = os.environ["PHOTO_OUTBOX_DIR"]
    seconds = float(os.environ.get("PHOTO_DECODE_SECONDS") or 20)
    print(f"photo-worker: watching the inbox, {seconds:g}s per photo", flush=True)
    while True:
        HEARTBEAT.touch()
        for ident in waiting(inbox):
            run_one(inbox, outbox, ident, seconds)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
