---
id: 95
title: "Canceling a job, and removing one created by mistake"
summary: "A canceled job stays as the same record with who canceled, who pressed the button and when, and frees its time at once; a job created by mistake is deleted with everything it left, unless a payment is recorded."
date: 2026-11-07
area: scheduling
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-07
supersedes: []
superseded_by: []
related: [docs/guides/booking-a-job.md, docs/reference/control-app.md, docs/reference/scheduling-and-calendars.md, docs/operations/importing-baserow.md, docs/architecture/data-model.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md]
---

# 0095: Canceling a job, and removing one created by mistake

**Status:** accepted · **Date:** 2026-11-07 · **Area:** scheduling

## Context

Until now **Cancel job** only set a job's status. A canceled job stayed on the schedule, faded, and nothing said who canceled or how much notice was given. A job booked by mistake could only be canceled, so it stayed in the customer's history as if the customer had canceled. After trying Phase 3, Step 2 the owner asked for three distinct outcomes.

## Decision

- **Cancel job opens a popup,** for managers only, on booked jobs: **Customer canceled**, **Dixie Detail canceled** and **Created by mistake**, and a way to close it without changing anything.
- **Customer canceled or Dixie Detail canceled** marks the job canceled. It stays as the same record with who canceled (the customer or the business), who pressed the button and when. It leaves every schedule view, the availability check, open times and every list of booked jobs, such as the pricebook's booked-job review, at once. The customer's page lists it under **Canceled jobs**, below the appointments, with its date and time, vehicle, services, quoted total, who canceled and how much notice was given: the time from the cancellation to the job's start.
- **Jobs canceled before this change,** and canceled jobs from the Baserow import, show as "Canceled" with no detail.
- **A canceled job stays canceled.** It is not marked booked or completed again; book a new job instead.
- **Created by mistake** asks once more ("Remove this job for good? This can't be undone."), then deletes the job as if it never existed: its lines, staff assignments, flags, rule overrides, settings-change listings, change history, and every quote it was priced from that nothing else uses. A series left with no visits is deleted too.
- **A job with a payment, an invoice or a paid helper can't be removed.** The message says so; cancel it instead.
- **A series visit** adds a choice in the popup: **This visit only** or **This and later visits**. The button pressed applies to that choice: the visit, or the visit and the series' later booked visits. A series with no booked visits left stops repeating.
- **The Baserow importer** imports a status of Canceled as a canceled job. An imported booked job missing from a fresh export is listed in the report for the owner, never removed. Baserow takes precedence over the app until the last import, before launch: a job canceled or removed only in the app comes back as Baserow has it on the next run. After that Baserow is retired.

## Alternatives considered

- **Delete a canceled job.** Loses the record of who canceled and how much notice they gave, which the owner wants to see on the customer's page.
- **Keep a deleted job's change history.** A job created by mistake should leave no trace; the history would show a job that never happened.
- **Remove a job missing from a fresh export.** The importer would delete jobs the owner may still want; listing them leaves the choice with the owner.

## Consequences

The schedule shows only jobs that will happen or have happened. Canceling frees the time for the website and the owner at once. A mistaken job removed in the app has to be removed in Baserow too, or it returns on the next import.
