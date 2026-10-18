---
id: 61
title: "Staff are authorized per service, and a manager assigns staff to each job"
summary: "One authorization record links each staff member to each service they may perform, edited from the staff page or the service page; qualified staff are offered first, and a lone qualified person is assigned automatically."
date: 2026-10-17
area: staff
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/reference/control-app.md, docs/architecture/data-model.md, data/booking-rules.yaml, docs/decisions/0053-check-and-trade-owner-only.md, docs/decisions/0056-scheduling-rules-are-settings.md]
---

# 0061: Staff are authorized per service, and a manager assigns staff to each job

**Status:** accepted · **Date:** 2026-10-17 · **Area:** staff

## Context

Helpers are paid by pay type (decision 0053), and assignments put a staff member on a job, but nothing recorded who may perform which service. As helpers learn more of the work, the owner needs to see who can do a job before assigning them, and to train people on services they aren't yet trusted with alone.

## Decision

- **One authorization record** links each staff member to each service they may perform. It covers every active service, add-ons included; history-only services are left out.
- **Two screens edit that same record:** the staff page (a person's services as toggles) and the service page (a service's staff as toggles). There is nothing to keep in sync.
- **Managers** (only the owner today) are authorized for every service. A new service starts with only managers authorized.
- **Assigning staff.** When a job is booked, the control app asks a manager to assign staff. Qualified staff are listed first; anyone else appears grayed out, with the services they aren't authorized for.
- **Two-person jobs.** The two people's authorizations together must cover every service on the job; neither needs all of them.
- **Training.** A manager can assign someone not yet authorized after a warning; the job records the reason.
- **Crew size.** Assigning a different number of people than the service's default recalculates time on site (crew time and the setup and breakdown split) and warns if the day no longer fits.
- **Automatic assignment.** When exactly one active staff member is qualified (today, always the owner), the app assigns them and skips the prompt. This is a setting, on by default.
- **Everyone assigned** gets the job and its time-to-leave alert.

## Alternatives considered

- **A list of services on each staff record and a separate list of staff on each service.** Two lists of the same facts would drift apart.
- **Require each person on a two-person job to cover every service.** Would stop a helper who does only interiors from joining a Full Detail with the owner.

## Consequences

The authorization record, both screens and the qualified list are built in Phase 1 Step 5b; the assign-staff prompt for each new website booking comes in Phase 3. While the owner works alone, automatic assignment means nothing changes day to day.
