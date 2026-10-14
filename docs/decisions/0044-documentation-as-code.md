---
id: 44
title: "Documentation lives in the repository as Markdown and YAML"
summary: "All documentation lives in the repository as Markdown and YAML with header blocks, written for humans and AI retrieval, and updated in the same pull request as the change."
date: 2026-10-13
area: documentation
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-13
supersedes: []
superseded_by: []
related: [docs/CONVENTIONS.md, docs/README.md]
---

# 0044: Documentation lives in the repository as Markdown and YAML

**Status:** accepted · **Date:** 2026-10-13 · **Area:** documentation

## Context

The owner plans to deploy AI across the business and needs it to be an expert on this system. During Phase 0 the docs drifted from reality several times, and knowledge was split across the repository, Claude docs and conversations.

## Decision

Adopt `docs/CONVENTIONS.md`: a folder layout by purpose, header blocks with audience, visibility and status, one decision per file, facts in `data/`, and an automatic check on every pull request. The executive plan, Phase 0 runbook and compliance drafts were migrated in on 2026-10-13 and frozen at their sources.

## Alternatives considered

- None recorded; the owner set this directly.

## Consequences

Every pull request that changes behaviour updates the docs. The docs are ready to load into a retrieval system.
