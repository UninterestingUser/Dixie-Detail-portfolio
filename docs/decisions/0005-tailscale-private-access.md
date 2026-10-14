---
id: 5
title: "Private access over Tailscale, with the server as its own node"
summary: "Staff reach the control app over the existing Tailscale network, and the server joins as its own node for HTTPS and to avoid subnet clashes."
date: 2026-10-07
area: network
status: accepted
audience: [owner, developer]
visibility: restricted
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/architecture/network-and-access.md]
---

# 0005: Private access over Tailscale, with the server as its own node

**Status:** accepted · **Date:** 2026-10-07 · **Area:** network

## Context

The control app must never be public. The owner already uses Tailscale, with pfSense advertising the home network 192.168.1.x, a range other Wi-Fi networks also use.

## Decision

The control app listens on the server's loopback address and is published to the tailnet with `tailscale serve`. The server is a Tailscale node in its own right, joined without `--accept-routes`, with key expiry disabled.

## Alternatives considered

- **Only the pfSense subnet route.** Breaks on outside networks that use the same address range, and gives no HTTPS address.
- **A public login page.** Exposes the control app to the internet.

## Consequences

The control app gets a real HTTPS address the Pixel can install as an app. Nothing listens on the LAN or the internet.
