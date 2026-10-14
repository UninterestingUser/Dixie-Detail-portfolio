---
id: 34
title: "Returning customers matched quietly by phone number"
summary: "A booking's mobile number is matched to existing customers and second contacts on the back end; differences are flagged for the owner, and nothing is shown to the customer."
date: 2026-10-11
area: customers
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/returning-customers.md]
---

# 0034: Returning customers matched quietly by phone number

**Status:** accepted · **Date:** 2026-10-11 · **Area:** customers

## Context

The owner wanted returning customers recognised without adding sign-in steps or exposing saved details.

## Decision

Match on 10 digits. A match attaches the booking; differences in name, address or vehicle are flagged with four resolution actions. The job uses the details as booked.

## Alternatives considered

- **Texted sign-in codes, a "booked before?" shortcut, remembered devices, rebooking links.** Deferred by the owner as more than needed for launch.

## Consequences

The booking flow is the same for everyone.
