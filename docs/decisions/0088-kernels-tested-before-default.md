---
id: 88
title: "A new kernel is booted once and must pass the gosu test before it becomes the GRUB default"
summary: "After kernel 7.0.0-42 hung gosu in the PostgreSQL containers under Docker's AppArmor profile, each new kernel is tried once with grub-reboot and kept only if the gosu test passes."
date: 2026-11-04
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-04
supersedes: []
superseded_by: []
related: [docs/operations/updating-the-kernel.md, docs/operations/troubleshooting.md, docs/architecture/server-and-stack.md, ops/gosu-test.sh]
---

# 0088: A new kernel is booted once and must pass the gosu test before it becomes the GRUB default

**Status:** accepted · **Date:** 2026-11-04 · **Area:** infrastructure

## Context

On 2026-11-03 the server ran Ubuntu kernel 7.0.0-42, and the PostgreSQL containers hung at start: the image's entrypoint switches to the postgres user with `gosu`, and under Docker's default AppArmor profile gosu hung there without logging an AppArmor denial. Kernel 7.0.0-38 works. Nothing stopped a new kernel from becoming the default before it had been tried with the stack.

## Decision

1. **A new kernel is never the GRUB default straight away.** GRUB boots a saved entry (`GRUB_DEFAULT=saved`), pinned by name to the kernel that works. A new kernel is booted once with `grub-reboot`, which applies to the next boot only.
2. **The gosu test decides.** On the new kernel the owner runs `ops/gosu-test.sh`, which starts `gosu` and a throwaway PostgreSQL from the stack's own image, and checks the stack. Only if both pass does `grub-set-default` make the new kernel the default. Otherwise a reboot returns to the working kernel.
3. **AppArmor stays on.** The stack is not run unconfined to get past a kernel that hangs; the working kernel stays the default instead.

The procedure is in [updating-the-kernel.md](../operations/updating-the-kernel.md).

## Alternatives considered

- **Hold kernel updates altogether.** It avoids the risk but also blocks security fixes, and a held kernel still has to be tested some day.
- **Run the database container with `apparmor=unconfined`.** It works around this hang by removing a layer of protection from the container that holds every customer record.
- **Let apt's newest kernel boot by default and fix problems afterwards.** Then the first sign of a bad kernel is a database that will not start.

## Consequences

- Each kernel update needs a planned reboot and a few minutes of the owner's time, outside working hours.
- A failed kernel never stays in charge: one reboot brings back the working one.
- The working kernel must stay installed while it is the default, so `apt autoremove` is read before it is answered.
