---
id: 57
title: "Calendar sync and conflict rules: the app writes Jobs, reads Time Off, and neither calendar changes an appointment"
summary: "The database is the only record of appointments; Jobs edits in Google are reset, hand-added Jobs events are flagged, every Time Off event blocks time, and clashes are flagged, never acted on."
date: 2026-10-17
area: calendar
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/scheduling-and-calendars.md, data/booking-rules.yaml, docs/decisions/0006-two-google-calendars.md, docs/decisions/0056-scheduling-rules-are-settings.md]
---

# 0057: Calendar sync and conflict rules

**Status:** accepted · **Date:** 2026-10-17 · **Area:** calendar

## Context

Decision 0006 set up two Google calendars: Jobs, written by the system, and Time Off, written by the owner. It did not say what happens when someone edits Jobs in Google, when Google is down, when time off lands on a booked job, or which Time Off events count. The owner settled these on 2026-10-17.

## Decision

The database is the only record of appointments. The app writes the Jobs calendar and reads the Time Off calendar; neither calendar ever changes an appointment.

**Jobs calendar.**

1. Each appointment has one event and one "Drive to job" block, linked by an ID stored on the appointment and in the event's private extended properties.
2. Booking, moving or canceling updates the events within a minute. If Google is down, the change queues and retries; a booking never waits for Google.
3. A Jobs event edited in Google is restored to the app's version at the next sync, and the control app notes the reset. A deleted Jobs event is recreated.
4. An event added to Jobs by hand counts as busy time and is flagged, so the owner can move it to Time Off or delete it. The app never deletes it.
5. Days closed in the control app show on Jobs as all-day "Closed" events.
6. A full check every night compares future appointments with Jobs and repairs any difference.

**Time Off calendar.**

1. An all-day event closes every day it covers.
2. A timed event blocks only its own time, plus the buffer setting (0 minutes at launch).
3. Every event counts, repeating events included. The Free/Busy setting is ignored, because Google marks all-day events "Free" by default.
4. Deleting an event reopens its time at the next check.
5. The app checks Time Off every 5 minutes and again when a booking is submitted.
6. Time off added over a booked appointment never cancels or moves it. The control app flags the clash and sends the owner a push alert to keep, reschedule or cancel the job.

**When Google is unreachable,** booking continues: Jobs changes queue, and availability uses the last copy of Time Off. If that copy is more than 60 minutes old, the control app shows a warning.

## Alternatives considered

- **Two-way sync, letting a Jobs edit in Google move the appointment.** It would make Google a second source of truth, against the ground rule that PostgreSQL is the only one.
- **Honor Google's Free/Busy setting on Time Off.** All-day events are "Free" by default, so a day off would silently stay open.
- **Cancel or move a job automatically when time off covers it.** The customer would be affected by a calendar entry the owner may not have meant that way; the owner decides.

## Consequences

The owner can block time from any calendar app without opening the control app, and a stray edit in Google cannot lose an appointment. The sync needs a queue, a nightly repair job and a Time Off poll; all are built in Phase 3. The check interval, buffer and stale-copy warning are settings (decision 0056).
