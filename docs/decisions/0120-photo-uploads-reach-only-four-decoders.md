---
id: 120
title: "Quote request photos reach only Pillow's four accepted decoders, on Pillow 13"
summary: "Pillow 12.3.0 had 43 open advisories, several critical, fixed only in 13.0.0. The app moves to 13.0.0, and Image.open tries only JPEG, PNG, WebP and HEIF, so no other decoder reads an upload."
date: 2026-11-21
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/decisions/0099-quote-requests-with-photos.md, app/publicapi/photos.py, app/requirements.txt, docs/reference/public-api.md]
---

# 0120: Quote request photos reach only Pillow's four accepted decoders, on Pillow 13

**Status:** accepted · **Date:** 2026-11-21 · **Area:** booking

## Context

Quote request photos (decision 0099) come from the public internet: anyone who passes Turnstile can open an upload session and send files. The app opens each one with Pillow to make a clean JPEG. On 2026-11-21 Pillow 12.3.0 had 43 open Dependabot alerts, several critical: heap overflows in JPEG and FlashPix decoding, TIFF writing and others, and many denial-of-service bugs in the TIFF, GIF, PDF, MPO and other decoders. All are fixed only in 13.0.0, a major version, which Dependabot had not proposed.

The app checked the format, but only after `Image.open` had returned. By then whichever of Pillow's decoders recognized the bytes had already parsed the file's header, so a crafted TIFF, GIF or PDF reached code the site never needs.

## Decision

- **Pillow 13.0.0.** pillow-heif 1.8.1, which reads iPhone photos, accepts it.
- **Only four decoders ever read an upload.** `Image.open` is given `formats=("JPEG", "PNG", "WEBP", "HEIF")`, so Pillow tries no other; a file in any other format is refused as `not_an_image` before any of it is parsed. A test proves the TIFF decoder is never called, and fails without the restriction.
- **A multi-picture JPEG is accepted, first picture only.** Some Android phones and cameras save a JPEG with a second picture in it, which Pillow opens through its JPEG decoder as "MPO". The app refused those before, telling the customer the photo couldn't be opened. It now keeps the first picture, the photo itself, and never seeks to the others.

## Alternatives considered

- **Pillow 13 alone.** Fixes today's advisories, but leaves every decoder the site doesn't need open to the next ones.
- **Check the file's first bytes before Pillow sees it.** The same protection, written by hand; Pillow's own `formats` argument does it with the decoders' own detection.

## Consequences

The next Pillow security bug in an unused format can't be reached through the upload. Pillow's next major version comes from Dependabot as its own pull request (decision 0118), and the photo tests check it, including the HEIC, PNG, WebP and multi-picture photos.
