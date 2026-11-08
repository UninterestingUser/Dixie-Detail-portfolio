---
id: 98
title: "The Google Calendar sync: a queue in PostgreSQL, a worker container and a nightly check"
summary: "Jobs calendar changes are queued in PostgreSQL with the booking; a worker container pushes them within seconds and copies Time Off every 5 minutes; a nightly timer runs the full check."
date: 2026-11-07
area: calendar
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-07
supersedes: []
superseded_by: []
related: [docs/decisions/0057-calendar-sync-and-conflict-rules.md, docs/decisions/0006-two-google-calendars.md, docs/reference/scheduling-and-calendars.md, docs/operations/connecting-the-google-calendars.md, docs/operations/monitoring.md, docs/reference/configuration.md]
---

# 0098: The Google Calendar sync: a queue in PostgreSQL, a worker container and a nightly check

**Status:** accepted · **Date:** 2026-11-07 · **Area:** calendar

## Context

[Decision 0057](0057-calendar-sync-and-conflict-rules.md) set what the sync must do: Jobs changes within a minute and retried while Google is down, a booking that never waits for Google, edits in Google put back, hand-added events flagged, Time Off copied every 5 minutes and when a booking is sent, and a nightly full check. It left how to build it to Phase 3, Step 3. The queue must survive restarts.

## Decision

**The queue is a table in PostgreSQL.**
- Saving an appointment, one of its lines or a closed date adds a task to `SyncTask` for its link: "job:" and the appointment's calendar key, or "closed:" and the date. The task is written in the same database transaction as the change, so a change is never lost and never pushed before it is saved.
- A later change to the same link folds into the same row and raises its version. A worker that pushed an older version leaves the task for the next pass.
- Each push makes Google match the database at that moment, so pushing twice does no harm.

**A worker container runs the queue.**
- `calendar-worker` in `compose.yaml` runs `python manage.py calendar_worker` from the app image, with the same settings and secret files as the app.
- Every 5 seconds it takes the due tasks with `FOR UPDATE SKIP LOCKED` and a 2-minute claim, then pushes them.
- A failed push waits 30 seconds, doubling each time up to 15 minutes, and is tried again.
- Every Time Off check (5 minutes at launch) it also:
  - copies the Time Off calendar
  - flags clashes
  - checks the Jobs calendar for edits made in Google.
- It survives restarts:
  - The queue is in the database.
  - A claim held by a stopped worker runs out after 2 minutes.
  - Docker restarts the container.
- A PostgreSQL advisory lock keeps the worker and the nightly check from writing the Jobs calendar at the same time, so neither takes the other's change for an edit in Google.

**The nightly full check is a systemd timer,** like the other scheduled jobs.
- `dixie-calendar-check.timer` runs `ops/calendar-check.sh` at 3:35 AM. The script runs `python manage.py sync_calendars` in a one-off app container.
- It pings the new Healthchecks check with the one-line summary, or with a failure when Google could not be asked.
- The same command is the first run, with `--dry-run` to print the events first.

**Event IDs come from the database.**
- Each appointment has a calendar key (a UUID).
- Its job event's ID is "job" plus the key, and its Drive to job block's is "drive" plus the key. A closed day's is "closed" plus the date.
- The link is also in each event's private extended properties.
- So the app can update, restore or delete an event without searching for it first. Updating an event deleted in Google brings it back.
- An event without the private properties was added by hand.

**What counts as an edit in Google.** The app stores a fingerprint of the title, location, notes, start and end it last wrote.
- An event in Google that differs from what the database wants, but still matches what the app last wrote, is an app change on its way. It is updated without a note.
- One that differs from what the app last wrote was edited in Google. It is put back, and the home screen and the job note it.

**Access.**
- The service account asks only for the `calendar.events` scope, so it can read and write events on the calendars shared with it and nothing else.
- Its JSON key is the Bitwarden secret `GOOGLE_SERVICE_ACCOUNT_JSON`. `ops/stack-start.sh` writes it to the in-memory secrets folder, and the app and the worker read it from `/run/secrets`; it is never in `.env`.
- The app signs its token requests with the `cryptography` library and calls the Calendar API over HTTPS directly, without Google's client library.

**The leave buffer is a setting.** The 10 minutes added to the drive time for the Drive to job block, and later the time-to-leave alert, is `leave_buffer_minutes` on the scheduling settings screen, seeded from `data/booking-rules.yaml`.

**Clashes are flagged, not pushed yet.** Time Off over a booked job shows on the home screen with **Keep**, **Reschedule** and **Cancel**. The push alert that decision 0057 also calls for comes with the push notifications in Phase 4.

## Alternatives considered

- **Push to Google during the booking request, or in a thread after it.** The booking would wait for Google, or a change would be lost when the app restarted.
- **A task queue such as Celery with Redis.** It needs another service and a broker to back up and watch. PostgreSQL already holds every booking and can hold the queue in the same transaction.
- **Run the worker inside the web app's processes, or from a systemd timer every minute.** Gunicorn's workers come and go, and a timer every minute would start a container each time. A long-running container is simpler and reacts within seconds.
- **Google's API client library.** Its dependencies are larger than the four calls the sync needs. One small, pinned crypto library signs the token.
- **Find events by searching the private properties.** It costs a search per change. IDs made from the calendar key need none.

## Consequences

- A booking writes one extra row, and the Jobs calendar follows within seconds.
- While Google is down, changes wait in the queue, and the control app warns once the Time Off copy is over an hour old.
- The stack has one more container. The nightly check alerts the owner through Healthchecks when the calendars can't be repaired.
