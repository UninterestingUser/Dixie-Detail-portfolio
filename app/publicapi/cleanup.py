"""The nightly cleanup (clean_public_api, run by dixie-api-cleanup.timer):

- photos never attached to a sent request, a day after they were uploaded;
- a closed request's photos, QUOTE_REQUEST_PHOTO_DAYS after it was declined
  or its job was done or canceled (the description stays);
- files in the photo folder with no record, such as a half-written upload;
- places no quote refers to, rate counts and smoke test passes, a day old.
"""

import datetime
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from . import photos
from .models import QuotePhoto, QuoteRequest, RateCount, SmokeTestPass, UploadSession, VerifiedPlace

DAY = datetime.timedelta(days=1)


@dataclass
class Cleaned:
    unattached_photos: int = 0
    closed_request_photos: int = 0
    stray_files: int = 0
    places: int = 0

    def __str__(self):
        return (
            f"Public API cleanup: {self.unattached_photos} unattached photo(s), "
            f"{self.closed_request_photos} photo(s) of closed requests, {self.stray_files} stray file(s) "
            f"and {self.places} unused place(s) deleted"
        )


def closed_requests(cutoff):
    """Requests with photos that closed before cutoff."""
    waiting = QuoteRequest.objects.filter(photos__isnull=False).distinct().select_related("appointment")
    return [
        request for request in waiting
        if (closed := request.closed_on()) is not None and closed < cutoff
    ]


def run(now=None):
    now = now or timezone.now()
    cleaned = Cleaned()
    cleaned.unattached_photos = photos.delete_photos(QuotePhoto.objects.filter(request__isnull=True, uploaded_at__lt=now - DAY))
    UploadSession.objects.filter(expires_at__lt=now - DAY, photos__isnull=True).delete()

    cutoff = now - datetime.timedelta(days=settings.QUOTE_REQUEST_PHOTO_DAYS)
    for request in closed_requests(cutoff):
        count = photos.delete_photos(request.photos.all())
        request.photos_deleted_at = now
        request.photos_deleted_count += count
        request.save(update_fields=["photos_deleted_at", "photos_deleted_count"])
        cleaned.closed_request_photos += count

    folder = settings.QUOTE_PHOTO_DIR
    if folder.exists():
        known = set(QuotePhoto.objects.values_list("file_name", flat=True))
        for path in folder.iterdir():
            if path.is_file() and path.name not in known and path.stat().st_mtime < (now - DAY).timestamp():
                path.unlink(missing_ok=True)
                cleaned.stray_files += 1

    cleaned.places, _ = VerifiedPlace.objects.filter(created_at__lt=now - DAY, quotes__isnull=True).delete()
    RateCount.objects.filter(window_start__lt=now - DAY).delete()
    SmokeTestPass.objects.filter(expires_at__lt=now).delete()
    return cleaned

