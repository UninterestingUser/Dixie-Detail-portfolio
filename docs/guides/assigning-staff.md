---
title: Assigning staff and the services they may do
summary: How to set which services each staff member is authorized for, from the staff page or the service page, and how to assign one or two people to a job, including someone in training.
audience: [owner, staff]
visibility: internal
status: current
updated: 2026-10-18
tags: [guides, staff, authorization, assignment, control-app]
related: [docs/reference/control-app.md, docs/decisions/0061-staff-authorized-per-service.md, docs/decisions/0069-booking-staffing-and-publishing-in-the-control-app.md, docs/guides/booking-a-job.md, data/booking-rules.yaml]
---

# Assigning staff and the services they may do

Each staff member is authorized for the services they may perform. The control app uses that to offer the right people for each job ([decision 0061](../decisions/0061-staff-authorized-per-service.md)). Only a manager, today the owner, changes authorizations or assigns someone not yet authorized.

## Set who may do what

There are two ways to the same setting; use whichever is handier.

- **By person:** tap **Staff**, then the person. Each active service, add-ons included, has a switch. Turn it on to authorize them; it saves at once.
- **By service:** tap **Staff**, then **Services and who can do them**, then the service. Each active staff member has a switch.

A manager is authorized for every service, including a service added later, so their switches are on and cannot be turned off. A new service starts with only managers authorized. Past services no longer on the price list do not appear. Each change records who made it and when.

Staff members are added in the Django admin, under **Staff members**, until a staff screen for that is built.

## Assign staff to a job

1. Open the job from the schedule. The **Staff** section lists every active staff member: qualified people first, then the rest, grayed out, with the services they are not authorized for.
2. Tick one or two people and tap **Save staff**.

- **Two people** are fine when together they are authorized for every service on the job; neither needs all of them. A helper who does interiors can join a Full Detail with the owner.
- **Someone not yet authorized**, for training: tick them and tap **Save staff**. A warning names the services no one on the crew is authorized for. Type the reason, such as "Training on carpet extraction", and tap **Assign anyway**. The reason is kept on that person's assignment and shown on the job. Only a manager sees **Assign anyway**.
- **A different crew size** than the job was booked with recalculates its service time and time on site: two people take 60% of the service time and half the setup and breakdown. The price does not change. A warning appears if the job now overlaps another that day.
- To take everyone off a job, untick them all and tap **Save staff**.

## Automatic assignment

When a one-person job is booked and exactly one active staff member is qualified (today, always the owner), that person is assigned at once and the job says so. A two-person job, such as Monthly Maintenance, always waits for you to pick the crew. The setting is `staff_assignment.automatic_when_one_qualified` in [data/booking-rules.yaml](../../data/booking-rules.yaml), on at launch; it moves to the settings screen in Phase 3.
