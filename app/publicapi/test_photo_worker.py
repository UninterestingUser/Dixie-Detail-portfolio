"""The photo worker (decision 0123): uploads go through the inbox and come
back from the outbox, one at a time, each decoded in a fresh process with a
time limit; a failed, crashed, timed-out or missing worker refuses the
photo, and nothing is left behind in either folder."""

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from django.test import override_settings
from PIL import Image

from photoworker import worker

from .test_quote_requests import QuoteRequestTestCase
from .testing import gps_exif, jpeg


class Worker:
    """The worker's loop in a thread, as the photo-worker container runs it."""

    def __init__(self, inbox, outbox, seconds):
        self.inbox, self.outbox, self.seconds = inbox, outbox, seconds
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stop.is_set():
            for ident in worker.waiting(self.inbox):
                worker.run_one(self.inbox, self.outbox, ident, self.seconds)
            time.sleep(0.02)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(timeout=10)


class PhotoWorkerTests(QuoteRequestTestCase):
    def setUp(self):
        super().setUp()
        made = []
        for prefix in ("dixie-photos-", "dixie-inbox-", "dixie-outbox-"):
            folder = tempfile.mkdtemp(prefix=prefix)
            self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
            made.append(folder)
        self.photo_dir, self.inbox, self.outbox = made
        patch = override_settings(
            QUOTE_PHOTO_DIR=Path(self.photo_dir), PHOTO_INBOX_DIR=self.inbox, PHOTO_OUTBOX_DIR=self.outbox,
            PHOTO_DECODE_SECONDS=20, PHOTO_DECODE_WAIT_SECONDS=30,
        )
        patch.enable()
        self.addCleanup(patch.disable)

    def assert_boxes_empty(self):
        self.assertEqual(os.listdir(self.inbox), [])
        self.assertEqual(os.listdir(self.outbox), [])

    def test_a_photo_goes_through_the_worker_and_comes_back_clean(self):
        original = jpeg((4000, 3000), exif=gps_exif())
        with Worker(self.inbox, self.outbox, 20):
            uploaded = self.upload(self.session(), original)
        self.assertEqual((uploaded["width"], uploaded["height"]), (2560, 1920))
        [stored] = os.listdir(self.photo_dir)
        saved = (Path(self.photo_dir) / stored).read_bytes()
        self.assertNotIn(b"MadeUpCameraCo", saved)
        with Image.open(Path(self.photo_dir) / stored) as image:
            self.assertEqual((image.format, image.size), ("JPEG", (2560, 1920)))
        # The original is deleted, and the result taken: nothing is left.
        self.assert_boxes_empty()

    def test_a_file_that_is_not_a_photo_is_refused_through_the_worker(self):
        with Worker(self.inbox, self.outbox, 20):
            answer = self.upload(self.session(), b"%PDF-1.7 not a photo", expect=422)
        self.assertEqual(answer["error"], "not_an_image")
        self.assertEqual(os.listdir(self.photo_dir), [])
        self.assert_boxes_empty()

    def test_a_decode_that_runs_out_of_time_is_a_refused_photo(self):
        slow = [sys.executable, "-c", "import time; time.sleep(30)"]
        with mock.patch.object(worker, "DECODE_COMMAND", slow), Worker(self.inbox, self.outbox, 0.5):
            started = time.monotonic()
            answer = self.upload(self.session(), jpeg(), expect=422)
        self.assertEqual(answer["error"], "not_an_image")
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(os.listdir(self.photo_dir), [])
        self.assert_boxes_empty()

    def test_a_decoder_that_crashes_is_a_refused_photo(self):
        crash = [sys.executable, "-c", "import os; os.abort()"]
        with mock.patch.object(worker, "DECODE_COMMAND", crash), Worker(self.inbox, self.outbox, 20):
            answer = self.upload(self.session(), jpeg(), expect=422)
        self.assertEqual(answer["error"], "not_an_image")
        self.assert_boxes_empty()

    def test_with_the_worker_down_the_upload_waits_then_refuses_and_cleans_up(self):
        with override_settings(PHOTO_DECODE_WAIT_SECONDS=0.5):
            answer = self.upload(self.session(), jpeg(), expect=422)
        self.assertEqual(answer["error"], "not_an_image")
        self.assertEqual(os.listdir(self.photo_dir), [])
        self.assert_boxes_empty()

    def test_photos_are_taken_one_at_a_time_oldest_first(self):
        for n, ident in enumerate(["b" * 32, "a" * 32]):
            path = Path(self.inbox) / f"{ident}.upload"
            path.write_bytes(jpeg())
            os.utime(path, (1_000_000 + n, 1_000_000 + n))
        (Path(self.inbox) / ("c" * 32 + ".part")).write_bytes(b"still being written")
        self.assertEqual(worker.waiting(self.inbox), ["b" * 32, "a" * 32])
