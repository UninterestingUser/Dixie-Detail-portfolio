---
id: 11
title: "The price matrix supersedes every price on the old website"
summary: "The owner's price matrix of 90 prices is the only price source; the old website's figures disappear at launch."
date: 2026-10-07
area: pricing
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/reference/pricing.md, data/price-matrix.csv]
---

# 0011: The price matrix supersedes every price on the old website

**Status:** accepted · **Date:** 2026-10-07 · **Area:** pricing

## Context

The website showed out-of-date prices, such as $80 for headlight restoration.

## Decision

Load `data/price-matrix.csv` as the pricebook. Every page and the booking flow read prices from the database.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Headlight Restoration is $95. Prices are never hard-coded.
