---
id: 100
title: "The public API: unguessable quotes, a day lock on booking, signed offline requests and test records"
summary: "Unguessable quote numbers that expire after a setting; Turnstile, quote and time checked in one transaction under a per-day lock; signed offline requests; test records and a smoke test."
date: 2026-11-08
area: booking
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-08
supersedes: []
superseded_by: []
related: [docs/reference/public-api.md, docs/reference/booking-flow.md, docs/architecture/network-and-access.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/decisions/0038-two-doors-access-model.md, docs/decisions/0099-quote-requests-with-photos.md, docs/reference/configuration.md]
---

# 0100: The public API: unguessable quotes, a day lock on booking, signed offline requests and test records

**Status:** accepted · **Date:** 2026-11-08 · **Area:** booking

## Context

Phase 3, Step 4 builds the public API the website calls ([public-api.md](../reference/public-api.md)). [Decision 0059](0059-quoted-price-is-price-of-record.md) says a booking refers to a server-issued quote; [decision 0038](0038-two-doors-access-model.md) says only `/health` and `/api/public/` reach the internet. The owner asked for quotes that expire after a setting, a booking that can't double-book a time, an offline "request a time" path, abuse controls, test records and an end-to-end smoke test. How to build each was left to this step.

## Decision

- **Quotes have unguessable numbers.** A website quote's number is ten random letters and digits, and a booking reference eight, from an alphabet without look-alike characters. A sequential number would let anyone read other visitors' quotes, which hold the address they typed.
- **A quote expires after `QUOTE_LIFETIME_MINUTES`** (120 to start). Booking an expired quote, or one the day of service would price differently (another pricebook version or tax rate in effect then), returns a fresh quote for the customer to confirm, never a silent new price.
- **One transaction, one lock per day.** A booking checks the Turnstile token, the quote's age and the time in one database transaction, after taking a PostgreSQL advisory lock keyed on the date. A second booking for the same day waits for the first to commit, then the availability check sees its job. The quote's one-to-one link to its appointment stops one quote booking twice.
- **Open times never call Google.** The public list estimates drives not already cached, so visitors browsing times can't use up the day's Routes calls; the booking checks the time with real drive times.
- **Offline requests are signed, not Turnstile-checked.** A Turnstile token expires in 5 minutes, long before a replay. Cloudflare's piece checks the token when the customer sends the form and signs each replay with a new Bitwarden secret, `OFFLINE_REQUESTS_SIGNING_KEY` (HMAC-SHA256 over a timestamp and the body, valid 5 minutes). The website's request id makes a second replay harmless.
- **Rate limits are counted in PostgreSQL**, per visitor address and kind, so the three app workers share one count. The address, Cloudflare's `CF-Connecting-IP`, is stored only as a keyed hash.
- **Consent wording lives in a data file** ([data/consent-wording.yaml](../../data/consent-wording.yaml)) by version. The website shows the current version; the server records each answer with the words of the version sent back, from the file.
- **Test records.** Customers and appointments get a test flag, set for bookings and requests from a number in `TEST_PHONE_NUMBERS`. Test jobs stay off the Jobs calendar; `delete_test_records` removes them.
- **The smoke test goes through the real public address** and uses a one-time pass it writes to the database in place of a Turnstile token. Only something with database access can make one, so it opens nothing to the internet.
- **Until quiet matching (Step 5), every booking and request creates a new customer.** Answers are built only from the quote, the place and the request, so matching changes nothing a customer sees.

## Alternatives considered

- **Sequential quote numbers.** Simple, but enumerable.
- **Re-pricing an expired quote silently at booking.** Breaks "the price shown is the price booked".
- **`SELECT … FOR UPDATE` on the day's appointments.** Locks nothing when the day is empty, which is exactly when two first bookings race.
- **A unique constraint on the start time.** Two jobs at different times can still clash on the same day; only the availability check knows.
- **Rate limits in process memory.** Each gunicorn worker would count separately.
- **Turnstile on replayed offline requests.** The tokens have expired by then.
- **A test mode switch on the API.** Anyone who found it could use it; a database pass can't be found from outside.

## Consequences

The website can price, show times and book with the server as the only judge of price and time. Two new secrets (`TURNSTILE_SECRET_KEY`, `OFFLINE_REQUESTS_SIGNING_KEY`) go in Bitwarden and seven new settings in `.env`; until the Turnstile key exists every booking is refused. Bookings for one day are checked one at a time, which at this business's volume costs nothing.
