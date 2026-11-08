---
id: 99
title: "Quote requests, with optional photos, for jobs the site can't price"
summary: "Any vehicle in a class booked by quote gets a quote request with a description and up to 6 cleaned photos, uploaded one by one, seen only in the control app and deleted 90 days after the request closes."
date: 2026-11-08
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-08
supersedes: []
superseded_by: []
related: [docs/reference/public-api.md, docs/reference/booking-flow.md, docs/decisions/0083-applying-the-size-based-classes.md, docs/operations/backups-and-restore.md, docs/decisions/0089-backup-rides-out-a-slow-drive.md, data/vehicle-classes.yaml]
---

# 0099: Quote requests, with optional photos, for jobs the site can't price

**Status:** accepted · **Date:** 2026-11-08 · **Area:** booking

## Context

Full-size Vans are booked by quote and priced by hand ([decision 0083](0083-applying-the-size-based-classes.md)), and their photo card said "Send us a photo for a quote", with nowhere to send it. Later classes, such as RVs or boats, may be priced the same way. Photos help the owner price a job, but they come from phones: large, in the iPhone's HEIC format, and carrying the customer's location. The owner set the rules for Phase 3, Step 4 on 2026-11-08.

## Decision

- **One path for every class booked by quote.** A vehicle whose class is set to "Ask for a quote" gets a quote request instead of a quote. Today that is Full-size Vans; a later class booked by quote uses it with no new code. A vehicle booked online is sent back to booking.
- **What a request holds:** the vehicle (year, make and model, or the photo card), the service wanted or "Not sure", a required description of what's needed, the service address, the name, mobile number, the two consent answers, and an optional note on preferred days. It is not an appointment and holds no time; the answer tells the customer the owner will reply with a price.
- **Photos are optional:** up to 6 per request and up to 15 MB each as sent, both settings. JPEG, PNG, WebP and HEIC are accepted.
- **Each photo uploads on its own** as the customer picks it, so one slow photo never loses the form, through an upload session the server opens after a Turnstile check, with the rate limits applied. Photos never attached to a sent request are deleted after a day.
- **Every photo is opened as an image** and refused if it is anything else or has an absurd pixel count (over 64 million). The server keeps a new JPEG, at most 2,560 pixels on the long side, with all metadata removed, location included. The original is never written to disk.
- **Stored under random names on the server** (`/srv/dixie-quote-photos`), never returned by any public endpoint, and seen only in the control app over Tailscale.
- **Kept 90 days after the request closes** (a setting): declined, or its job done or canceled. The description stays.
- **Backed up nightly**: the photo folder is mirrored to the RAID and sent to the restic repository tagged `photos`, after the dump's forget/prune, in one attempt of at most 8 minutes. The restore test reports how many photos the newest photo snapshot holds.
- **The Full-size Vans card says "Ask for a quote"** in [data/vehicle-classes.yaml](../../data/vehicle-classes.yaml) and, through a migration, in the database unless the owner has changed it.

## The backup's time limit still fits

[Decision 0089](0089-backup-rides-out-a-slow-drive.md) limits each restic attempt to 8 minutes and fits the worst case into the unit's and the Healthchecks check's 2 hours. The photo upload was checked against both:

- **One attempt fits in 8 minutes by a wide margin.** restic sends only photos it has not stored before. Each stored photo is a cleaned JPEG of roughly 0.3 to 1.5 MB, so even ten six-photo requests in a day are under 100 MB, about a minute and a half at a slow 10 Mbit/s upload. Reading the folder and the repository index is the same work the dump's upload already does in seconds.
- **The worst case still fits 2 hours.** One more attempt of at most 9 minutes (8, plus the minute before SIGKILL) takes the longest run from about 1 hour 43 minutes to about 1 hour 52 minutes, and the start-to-last-ping time from about 1 hour 38 to about 1 hour 47 minutes.
- **No retries for photos.** Three attempts with the 5- and 15-minute waits would add 47 minutes and pass 2 hours. A night whose photo upload fails is reported like any failure, the RAID mirror already holds the photos, and the next night sends whatever was missed.

## Alternatives considered

- **Photos in the request itself.** One slow photo on a phone connection would lose the whole form.
- **Keep the original files.** They carry the customer's location and can be tens of megabytes; nothing the owner needs is lost at 2,560 pixels.
- **Retry the photo upload like the dump.** Breaks the 2-hour worst case for data the RAID already holds.
- **Photos required.** Many customers can describe the job well enough, and a required photo loses requests.

## Consequences

The owner gets every job the site can't price as a request with its description and photos, without a call. A new class booked by quote needs only its class setting. The backup carries a new folder and a fourth restic step; anyone changing the backup's limits checks the worst case with this step included.
