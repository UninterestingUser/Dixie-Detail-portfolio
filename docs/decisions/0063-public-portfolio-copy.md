---
id: 63
title: "The working repository stays private; a rewritten public copy serves as a portfolio"
summary: "The owner publishes a separate public copy of the repository, with every commit rewritten to hide server addresses and private details, instead of making the working repository public."
date: 2026-10-17
area: repository
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-10-17
supersedes: []
superseded_by: []
related: [docs/operations/publishing-the-portfolio.md, tools/publish-portfolio.sh, README.md, CLAUDE.md, docs/decisions/0044-documentation-as-code.md]
---

# 0063: The working repository stays private; a rewritten public copy serves as a portfolio

**Status:** accepted · **Date:** 2026-10-17 · **Area:** repository

## Context

The owner uses his GitHub repositories as part of his résumé for technical jobs. The working repository was made public briefly on 2026-10-17 for a review. A scan of every commit found no secrets, keys, customer names, customer phone numbers or addresses, but it did show the full infrastructure map (the server's network address, the tailnet name, folder paths, the backup design and the deploy flow), ten documents marked `visibility: restricted`, a personal note about the owner's family, and the owner's personal email on every commit. Later phases add the public booking API and the payment and texting integrations.

## Decision

- The working repository stays private.
- A separate public repository holds a copy built by `tools/publish-portfolio.sh`: it clones `main`, rewrites every commit with git filter-repo (text replacements and an email mapping), checks the result, and pushes.
- The replacement rules, the email mapping and the public URL live in `"$HOME/Dixie Detail/github-portfolio"` on the owner's workstation, never in a repository, because the rules name what they hide.
- The owner publishes at milestones. Because the rewrite gives the same result for the same input, updates add commits on top; a change to the rules needs a one-time force push.
- The public repository has secret scanning, push protection, Dependabot alerts and a ruleset that blocks force pushes and deletion of `main`.
- The README states openly how the system was built: the owner's role, Claude in the Claude app (planning and research), Claude Code (implementation) and Grok (second opinion).

## Alternatives considered

- **Clean the working repository in place and keep it public.** Rewriting history in place leaves the old commits reachable through the merged pull requests until GitHub Support purges them, needs every clone re-made, and keeps future code and restricted documents public by default.
- **Keep everything private.** Leaves the owner without a portfolio.
- **Publish a snapshot without history.** Simpler, but loses the commit history, which shows how the work was done.

## Consequences

- The private repository keeps real values where operations need them; new writing still follows the rule in `CLAUDE.md` to stay fit for publishing.
- Pull request discussions and issues stay private; the public copy carries the commits only.
- Publishing is a manual step with a review list, so a new private detail is caught by the owner before it goes out.
