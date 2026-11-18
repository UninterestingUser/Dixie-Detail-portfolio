---
title: Public API
summary: Every endpoint the website calls under /api/public/v1/, what each takes and answers, the quote, booking and quote request rules, and the abuse, privacy and test-record controls.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-18
tags: [api, booking, website, quotes, photos, phase-3]
related: [docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md, docs/decisions/0101-website-bookings-in-the-control-app.md, docs/guides/handling-website-bookings.md, docs/decisions/0100-public-api-quotes-and-bookings.md, docs/decisions/0099-quote-requests-with-photos.md, docs/reference/booking-flow.md, docs/architecture/network-and-access.md, docs/reference/configuration.md, docs/reference/pricing.md, docs/reference/returning-customers.md, docs/reference/text-messages.md, docs/decisions/0038-two-doors-access-model.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md, data/consent-wording.yaml]
---

# Public API

The public API is the only part of the app the internet can reach, at `https://api.dixiedetail.com/api/public/v1/`, through the Cloudflare Tunnel ([network-and-access.md](../architecture/network-and-access.md), [decision 0038](../decisions/0038-two-doors-access-model.md)). The website's booking form and its build call it. It was built in Phase 3, Step 4 (decisions [0099](../decisions/0099-quote-requests-with-photos.md) and [0100](../decisions/0100-public-api-quotes-and-bookings.md)); the code is in `app/publicapi/`.

It does what the booking form needs and nothing more: list services and prices, look vehicles up, check an address, price a job, show open times, take a booking, take a quote request with photos, and take an offline "request a time" form. Every answer is JSON. Prices are worked out only on the server: the website shows the server's numbers and does no arithmetic ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)).

## Endpoints at a glance

| Method and path | What it does | Rate limit kind |
| --- | --- | --- |
| `GET services` | The published pricebook: services, classes, size variants, condition levels, "from" prices. Cacheable | read |
| `GET booking-options` | Payment methods, the consent wording, how long a quote lasts, photo limits. Cacheable | read |
| `GET price-table` | The server's total and time on site for every job bookable online, for the website's build. Cacheable | read |
| `GET vehicles/years` | Model years in the catalog, newest first | read |
| `GET vehicles/makes?year=` | Makes with a model in that year | read |
| `GET vehicles/models?year=&make=` | Models of that make and year, motorcycles labeled | read |
| `GET vehicles/lookup?year=&make=&model=&type=&size=` | The `classify()` lookup: class, size, the question still to ask, or the photo cards | read |
| `GET vehicles/photo-cards` | The eight photo cards | read |
| `POST addresses` | A Google place ID becomes a verified address in the service area, with its tax rate | address |
| `POST quotes` | Prices a job and returns a numbered quote | quote |
| `GET open-times?quote=&from=&days=` | Open start times for a quote's time on site and address | read |
| `POST bookings` | Books a quote at a start time | booking |
| `POST quote-requests/uploads` | Opens an upload session for photos, after a Turnstile check | upload_session |
| `POST quote-requests/uploads/{session}/photos` | Uploads one photo | photo |
| `DELETE quote-requests/uploads/{session}/photos/{photo}` | Removes a photo picked by mistake | photo |
| `POST quote-requests` | Sends a quote request for a job the site can't price | quote_request |
| `POST time-requests` | An offline "request a time" form, replayed by Cloudflare and signed | offline |
| `POST quote-requests/offline` | An offline quote request, without photos, replayed by Cloudflare and signed | offline |

Cacheable answers carry `Cache-Control: public, max-age=300`; everything else carries `no-store`.

## Errors are generic

Every refusal is JSON with an `error` code and a plain `message` the website can show, plus `field` when one input is wrong. No answer ever carries a traceback, a scheduling rule's reason, or anything from a customer's record. A crash answers `500 server_error` with a "please try again or call" message and is logged on the server.

| Status | `error` | When |
| --- | --- | --- |
| 400 | `bad_request` | An input is missing, unknown, the wrong type, too long or holds control characters. `field` names it |
| 403 | `forbidden` | The browser's origin is not one of the website's addresses |
| 403 | `turnstile_failed` | The Turnstile token was refused, or no secret key is set |
| 404 | `not_found` | An unknown quote, session or photo |
| 405 | `method_not_allowed` | The wrong method for the path |
| 409 | `quote_expired`, `quote_changed` | The quote can't be booked as it is; the answer carries a fresh `quote` to confirm |
| 409 | `time_taken`, `quote_used` | The time is no longer open, or the quote was already booked |
| 413 | `too_large`, `photo_too_large` | A JSON body over 16 KB, or a photo over the size limit |
| 422 | `outside_area`, `not_an_address` | The address is outside the service area, or not a street address |
| 422 | `size_question`, `photo_card_needed`, `ask_for_quote`, `book_online`, `not_offered` | What the vehicle needs next (see below) |
| 422 | `not_an_image`, `too_many_photos` | A photo was refused |
| 429 | `rate_limited` | Too many requests from one visitor address |
| 503 | `unavailable` | Google or Cloudflare could not be asked just now, or no pricebook is published |

## The pricebook: GET services

The published pricebook in effect today, for the website build and the service cards:

- `pricebook_version`, `effective_date`;
- `classes`: each offered vehicle class with its `id`, `name`, `booked_by_quote`, photo card caption and examples, active `sizes` (value and label) and `from_price`, the lowest main-service price for the class (none for a class booked by quote);
- `condition_levels`: level, `adds_percent`, `booked_by_quote`, label and description. Level 3 is booked by quote, with `adds_percent` null: it has no price ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md));
- `services`: each service and add-on customers can book, with `kind` (`service` or `add_on`), description, `condition_applies` (true only for Full Detail and Interior Only, from the published version), `from_price` and every `prices` cell (class, size, price). Maintenance plans and custom lines are never listed.

These prices are for display: a booking always uses a quote the server issued.

## Vehicles: years, makes, models and the lookup

- **The lists** come from the catalog's classified model years. Makes are matched by their spellings in [data/vehicle-names.yaml](../../data/vehicle-names.yaml). Each model carries `type` (`vehicle` or `motorcycle`) and `motorcycle: true` for the "Motorcycle" label, so a Honda Gold Wing and a Honda Accord are easy to tell apart ([decision 0072](../decisions/0072-motorcycles-class.md)).
- **The lookup** runs `classify()` ([vehicle-classification.md](vehicle-classification.md#the-lookup)) and answers `class`, `size`, `question` (with `key`, `text` and `choices`, each choice's `answer` being the size value to send back as `size`), `booked_by_quote`, a short `message` such as "Medium identified.", and `photo_cards` when the vehicle is not in the catalog.
- **The photo cards** are one per offered class, each with its caption, examples, photo path and `booked_by_quote`. A class picked from a card is sent as `{"photo_card": <class id>}`. When the class has several sizes and no question settles them, such as Small's one row or two, the size question is built from the sizes' own labels.
- **A class booked by quote**, today only Full-size Vans, can't be booked online. The lookup says `booked_by_quote: true` with "Ask for a quote", and the site sends the customer to a quote request.

## Addresses: POST addresses

The body is `{"place_id": ..., "session_token": ...}` from Google Places Autocomplete. The server looks the place up with its own key, ending the autocomplete session ([booking-flow.md](booking-flow.md#address-entry-is-validated-as-the-customer-types)), then:

- refuses anything but a street address in the United States (`not_an_address`);
- refuses an address outside the service area with a polite message (`outside_area`), unless it matches an address the owner approved ([decision 0037](../decisions/0037-approved-out-of-area-addresses.md)): the same Google place, or the same house number, street and ZIP code;
- answers a `place` token, the address parts, `in_area`, `approved_out_of_area` and the `tax` line (rate and jurisdiction, from [sales-tax.md](sales-tax.md)), with the reminder that water and power are needed.

Coordinates from the browser are never used. Only places in the area are kept, and a place no quote uses is deleted after a day.

## Quotes: POST quotes

The body is `vehicle` (year, make, model and type, or a photo card), `size` (the answer to the size question), `condition`, `service`, `add_ons` and, once known, `place`. The answer is a numbered quote record:

- `number`: ten letters and digits, unguessable;
- `expires_at`: `QUOTE_LIFETIME_MINUTES` after it was issued (2 hours to start);
- the vehicle's description, class and size, the service and add-ons, the condition level;
- `lines` (kind, description, amount), `total_before_tax`, `sales_tax` (rate, amount and jurisdiction, or none before the address), `total`;
- `service_minutes`, `time_on_site_minutes` and `full_day`.

**The condition** is 1 to 3, and is taken only with a service that has `condition_applies`: Full Detail and Interior Only ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md)). It is required with them, and refused with anything else as a `bad_request` on the `condition` field. A level booked by quote, Level 3, has no price or time: the answer is `ask_for_quote` (422), with no quote issued, and a `quote_request` object holding the `service`, `condition` and `add_ons` to send on to a quote request.

A quote never changes. A changed input, such as another condition level or the address, makes a new quote. The quote is the pricing engine's quote record ([pricing.md](pricing.md#the-quoted-price-is-the-price-of-record)), so it holds the pricebook version and tax rates too. A vehicle that needs something else first is refused with what it needs: `size_question` (with the question), `photo_card_needed` (with the cards), `ask_for_quote`, or `not_offered` for a service or add-on the pricebook does not price for the class, such as anything but Motorcycle Detail for a motorcycle.

## Open times: GET open-times

The quote's number, an optional first date and a number of days (14 by default, 31 at most). The answer lists each day with its open start times, each as an Eastern ISO time and a label such as "8:00 AM", from the availability check with the quote's time on site and the place's location ([scheduling-and-calendars.md](scheduling-and-calendars.md)). Days run from the minimum notice to the furthest bookable date.

- Only open times are shown, never why a time is closed: the reasons name other customers' jobs and the owner's Time Off.
- Drives not already in the drive-time cache are estimated, never asked of Google, so visitors browsing times can't use up the day's Google Routes calls. The booking checks the time again with real drive times.

## Booking: POST bookings

The body is `quote`, `start`, `first_name`, optional `last_name`, `mobile`, `payment_method` (one of the website's methods), optional `color`, `consents` and `turnstile`. In one database transaction the server:

1. checks the Turnstile token;
2. refuses a quote already booked (`quote_used`);
3. returns a fresh quote to confirm when the quote has expired (`quote_expired`), or when the day of service would price it differently, under another pricebook version or tax rate (`quote_changed`); never a silent new price. A job the day's version books by quote, such as Level 3, gets no fresh quote: it is refused with `ask_for_quote`, so a Level 3 job is never booked online ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md));
4. takes a lock on the day, then runs the availability check with the quote's time on site, so two people can't book the same time: the second waits for the first and then sees its job (`time_taken`);
5. matches the mobile number quietly ([returning-customers.md](returning-customers.md)): a returning customer's booking goes on their record, with any difference in name, address or vehicle flagged for the owner, and a new number makes a new customer;
6. creates the address from the place and the vehicle with its color where the record doesn't already have them, the two consent records, and the appointment with the quote's lines as its line snapshot (decisions [0033](../decisions/0033-pricebook-versions-and-line-snapshots.md) and 0059);
7. assigns the only qualified staff member to a one-person job; any other job waits for a manager on the control app's home screen (decisions [0061](../decisions/0061-staff-authorized-per-service.md) and [0069](../decisions/0069-booking-staffing-and-publishing-in-the-control-app.md)).

The answer, `201`, carries the booking `reference` (eight letters and digits), a `summary` (service, add-ons, vehicle, color, arrival, time on site, address, totals, payment method and the "confirmed when we see the vehicle" notes) and a `calendar_file` (an iCalendar event, with its file name and content type).

**A second vehicle the same day.** When the matched customer already has a job on that day, the booking becomes a request the owner approves, not an appointment ([decision 0101](../decisions/0101-website-bookings-in-the-control-app.md)). The time must still be open. The answer is `202` with `request` (its reference), `status: "requested"`, a `message` that Dixie Detail will confirm by text or call, and the same `summary`, but no calendar file. The form shows the message instead of the booking confirmation.

The summary is built only from the quote, the place and this booking, never from a customer's record, so quiet matching changes nothing the customer sees. The color never changes the price ([decision 0067](../decisions/0067-color-tells-identical-vehicles-apart.md)).

## Consent is recorded with its exact wording

`GET booking-options` serves the current wording of the two consent checkboxes from [data/consent-wording.yaml](../../data/consent-wording.yaml), with its version. The booking, quote request or offline request sends back `{"version": ..., "appointment": true or false, "follow_up": true or false}`. The server records one consent row per kind, yes or no, with the words of that version from the data file, never words from the browser, the time and the source "Website booking form" ([text-messages.md](text-messages.md)). An unknown version is refused, so a page left open across a wording change reloads.

## Quote requests

A quote request is the path for any job the site can't price: any vehicle in a class booked by quote, today Full-size Vans ([decision 0099](../decisions/0099-quote-requests-with-photos.md)), and Full Detail or Interior Only at a condition level booked by quote, today Level 3 ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md)). A class or level the owner later sets to "Ask for a quote", such as RVs or boats, uses it with no new code. Any other job is refused with `book_online`, and a service or add-on the pricebook doesn't offer for the vehicle with `not_offered`.

1. **An upload session.** `POST quote-requests/uploads` with a Turnstile token answers a session token, good for 6 hours.
2. **Photos, one at a time.** Each photo uploads on its own as the customer picks it, as multipart form data in the field `photo`, so one slow photo never loses the form. Photos are optional: up to `QUOTE_REQUEST_MAX_PHOTOS` (6) per request, each up to `QUOTE_REQUEST_PHOTO_MAX_MB` (15 MB) as sent. JPEG, PNG, WebP and HEIC (the iPhone format) are accepted. A picked photo can be removed with `DELETE`.
3. **The request.** `POST quote-requests` with the vehicle (year, make and model, or the photo card with any year, make and model the customer knows), an optional `size` (the answer to the size question), `service` (a service id, or `"not_sure"`), an optional `condition` (only with Full Detail or Interior Only, as for a quote) and `add_ons`, a required `description` of what's needed (up to 2,000 characters), the `place`, the name, mobile number, the two consent answers, an optional `preferred_days` note, the `session` and the `photos` it keeps, and a Turnstile token. Photos picked but left out are deleted at once.

The answer is the request's `reference` and a message that Dixie Detail will reply with a price. A quote request is not an appointment and holds no time. It keeps the service, condition level and add-ons asked for. It is matched quietly like a booking, and an address or vehicle it brings waits off the customer's record until it is booked. The owner sees it in the "needs you" list on the control app's home screen and on **Account → Website requests**, prices it by hand into a quote, then books it from that quote into an open time or declines it ([control-app.md](control-app.md#website-bookings-and-requests)).

## Every photo is checked and cleaned

- The server opens every photo as an image and refuses anything else, and anything over 64 million pixels, before decoding it.
- It saves a new JPEG, at most 2,560 pixels on the long side, drawn into a fresh image, so no metadata of any kind survives: no location, no camera, no date, no color profile. The original is never written to disk.
- Photos are stored under random names in the photo folder (`/srv/dixie-quote-photos` on the server, mounted at `QUOTE_PHOTO_DIR` in the app container), readable by the app only.
- No public endpoint ever returns a photo or its file name. They are seen only in the control app, over Tailscale.

## How long photos are kept

The nightly cleanup (`clean_public_api`, run by `dixie-api-cleanup.timer` at 2:20 AM) deletes photos never attached to a sent request after a day, and a request's photos `QUOTE_REQUEST_PHOTO_DAYS` (90) after it is declined, or its job is done or canceled. The description stays, with a note of how many photos were deleted and when. The photo folder is in the nightly backup, and the restore test reports how many photos the newest backup holds ([backups-and-restore.md](../operations/backups-and-restore.md)).

## The price table: GET price-table

The website bakes this into the booking page when it is built, for the "request a time" form it shows while the server can't be reached ([booking-flow.md](booking-flow.md#when-the-server-cant-be-reached)). It lists every job bookable online, priced by the pricing engine: each offered class booked online and its sizes, each bookable service, each condition level with a price for a service that takes one (Level 1 and Level 2, never Level 3), and no add-on, each add-on alone, or both. Each entry is `class_id`, `size`, `service`, `condition`, `add_ons`, `total_before_tax`, `time_on_site_minutes` and `full_day`, with the `pricebook_version` and `effective_date` at the top. The browser only looks a total up; it never works one out ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)). Combinations the pricebook doesn't price are left out.

## Offline requests: POST time-requests

While the server can't be reached, or Google's address suggestions are down, the website's form becomes a "request a time" form priced from the price table, and Cloudflare's offline piece holds what the customer sends ([booking-flow.md](booking-flow.md#when-the-server-cant-be-reached), [decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md)). It first tries the server at once; when the server doesn't answer, it replays each one here every 5 minutes until it does ([decision 0100](../decisions/0100-public-api-quotes-and-bookings.md)).

- **Signed, not Turnstile.** A Turnstile token would have expired by the replay, so Cloudflare checks it when the customer sends the form, and signs each replay: `X-Dixie-Timestamp` (seconds since 1970, within 5 minutes) and `X-Dixie-Signature`, the hex HMAC-SHA256 of the timestamp, a period and the raw body, with the Bitwarden secret `OFFLINE_REQUESTS_SIGNING_KEY`. Anything else is refused with `401`.
- **The body** is the website's `request_id` (a UUID), `submitted_at`, the vehicle, size, condition, service and add-ons, the address, an optional `preferred_start` and note, the name, mobile, payment method, color, consents, and `shown`: the total before tax and pricebook version the customer saw.
- **The vehicle** is the year, make and model, or the photo card the customer picked with any year, make and model they typed.
- **The address** is the `place_id` (with its `session_token`) from Google's suggestions, or, when the suggestions were down too, the `address` as typed. Exactly one is sent. A typed address is kept unchecked, the job is priced without sales tax, and the request notes "Address typed while address suggestions were down, not checked" for the owner.
- **Priced on arrival.** The server looks the address up, prices the job from the pricebook in effect, matches the mobile number quietly, and keeps a request, not an appointment. When its total before tax differs from what the customer saw, the request is flagged "Price differs", in the "needs you" list too. An address outside the area, or a job that can't be priced, is kept with the problem noted. A second replay of the same `request_id` changes nothing. The owner books it, priced for the day picked, or declines it ([control-app.md](control-app.md#website-bookings-and-requests)).

## Offline quote requests: POST quote-requests/offline

A quote request sent while the server can't be reached, or while Google's address suggestions are down, is held and replayed by the same piece, signed the same way. It carries no photos: the form tells the customer they can text photos later. The body is the quote request's fields (vehicle, `size`, `service` or `"not_sure"`, `condition`, `add_ons`, `description`, name, mobile, consents, `preferred_days`) plus the website's `request_id`, `submitted_at`, and the `place_id` with its `session_token` or the `address` as typed. Nothing the customer sent is lost: an address that can't be checked, or a job the site would book online after all, is kept with the problem noted on the request for the owner. A second replay of the same `request_id` changes nothing.

## Abuse and privacy controls

- **Turnstile** on every booking, upload session and quote request. The server sends the token, its secret key (Bitwarden secret `TURNSTILE_SECRET_KEY`) and the visitor's address to Cloudflare's siteverify. With no secret key set, every such request is refused.
- **Rate limits per visitor address**, counted in PostgreSQL so every app worker sees the same count. The visitor's address is Cloudflare's `CF-Connecting-IP` on the public door, kept only as a keyed hash, and counts older than a day are deleted. The limits, per kind, are in `PUBLIC_API_RATE_LIMITS` in `app/dixie/settings_base.py`.
- **Size limits and strict validation** on every input: known fields only, the right types, lengths capped, no control characters, phone numbers of 10 digits (decision 0049), JSON bodies up to 16 KB, photos up to their limit.
- **CORS only for the site's addresses**, held in the setting `PUBLIC_API_CORS_ORIGINS`, each trimmed of spaces and a trailing slash when it is read ([configuration.md](configuration.md#the-public-api)). A browser on any other origin is refused; a request with no origin, such as the smoke test, is allowed. No cookies are set or read.
- **Generic errors** and **no customer data** in any answer, as above.

## Test records

Customers and appointments have a **test record** flag. A test record never goes on the Jobs calendar, shows a "Test" badge in the control app, the "needs you" list included, and is for every report to leave out as reports are built (the sales tax report and the GnuCash export, Phase 6). It is deleted by `python manage.py delete_test_records` (with `--dry-run` to count first), which deletes every test customer with their appointments, review flags, quote requests and photos, offline requests, second vehicle requests, the quotes their jobs and requests were priced from, vehicles, addresses and consents, in an order that never trips a protected reference ([decision 0102](../decisions/0102-removing-or-canceling-a-job-booked-from-a-request.md)). A booking or request from a mobile number in `TEST_PHONE_NUMBERS` is marked test automatically, and quiet matching puts it only on a test customer, never a real one.

`python manage.py api_smoke_test` checks the whole public path from the server:

1. It goes out through `https://api.dixiedetail.com` (`API_SMOKE_TEST_URL`), like a customer's browser.
2. It reads the pricebook, looks up a 2019 Toyota RAV4, checks the address `API_SMOKE_TEST_PLACE_ID` (a public place in the area, never a customer's), quotes an Exterior Only (with a condition level only if the published pricebook gives it one), books the first open time from the first test number, and sends a Full-size Vans quote request with one photo.
3. It checks both arrived as test records with the photo on disk, then deletes both, and prints `api-smoke-test: PASS`.

It can't solve a Turnstile widget, so it makes a one-time pass in the database, good for 10 minutes and ten uses, and sends that instead. Only something with the database can make one. Run it on the server with:

```
cd /srv/dixie-detail && docker compose run --rm --no-deps -T app python manage.py api_smoke_test
```

Two more scenarios try the control app's screens ([../guides/handling-website-bookings.md](../guides/handling-website-bookings.md#try-it-with-test-records)):

- `--scenario returning` makes a test customer with two identical 2019 Toyota RAV4s, white and dark blue, and an address elsewhere, then books three times through the public address at the smoke test's place, on three different days: a color that picks the dark blue one, a blank color and a color that matches neither. It checks the first gets an address flag only, and the other two an identical-vehicles flag each.
- `--scenario quote` sends a test quote request for a Full-size Vans vehicle, a 2021 Ford Transit from the photo card, with two photos.
- `--keep` leaves what a scenario made, for the owner to try the review queue and the request screens; `delete_test_records` removes it afterwards. Without it, the scenario deletes what it made, as the basic run does.

The two scenarios refuse to start while test records from an earlier run are still there, since a booking would match them instead; run `delete_test_records` first.
