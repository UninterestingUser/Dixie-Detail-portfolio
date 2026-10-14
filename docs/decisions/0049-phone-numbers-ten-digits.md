---
id: 49
title: "Phone numbers are stored as 10 digits"
summary: "Phone numbers are stored as their 10 digits with no formatting or country code, so matching a returning customer by number is a plain comparison."
date: 2026-10-14
area: customers
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-14
supersedes: []
superseded_by: []
related: [docs/reference/returning-customers.md, docs/decisions/0034-quiet-customer-matching.md, docs/architecture/data-model.md]
---

# 0049: Phone numbers are stored as 10 digits

**Status:** accepted · **Date:** 2026-10-14 · **Area:** customers

## Context

Returning customers are matched quietly by phone number (decision 0034). The same number arrives typed as `(615) 555-0142`, `615.555.0142`, `+1 615 555 0142` or `6155550142`. Every customer is in the United States.

## Decision

- A phone number is stored as exactly 10 digits, such as `6155550142`, with no spaces, punctuation or `+1`.
- On the way in, the app removes everything but digits and drops a leading `1` from an 11-digit number. Anything that is not then 10 digits is rejected with a plain message.
- Screens and messages show it formatted, such as `(615) 555-0142`.
- The `+1` is added only when a number is handed to an outside service that requires it, such as the texting provider.

## Alternatives considered

- **International format (`+16155550142`).** Adds the same prefix to every number for no benefit while every customer is in the United States.
- **Store what was typed.** Matching would break on formatting differences.
- **A phone-number library.** More than a single-country business needs.

## Consequences

Matching a returning customer is an exact comparison, which a database index makes fast. A number from outside North America cannot be stored; if the business ever needs one, that is a new decision.
