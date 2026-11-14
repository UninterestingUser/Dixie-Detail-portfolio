---
id: 104
title: "The public portfolio copy leaves out the vehicle class pictures"
summary: "tools/publish-portfolio.sh drops website/public/images/vehicle-classes/ from every commit of the public copy, because the business shows those pictures on its own site but holds no license to redistribute them."
date: 2026-11-14
area: repository
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-14
supersedes: []
superseded_by: []
related: [docs/decisions/0063-public-portfolio-copy.md, docs/operations/publishing-the-portfolio.md, tools/publish-portfolio.sh, docs/reference/website-and-seo.md]
---

# 0104: The public portfolio copy leaves out the vehicle class pictures

**Status:** accepted · **Date:** 2026-11-14 · **Area:** repository

## Context

The website's eight vehicle class pictures (`website/public/images/vehicle-classes/`) are third-party renders. The owner chose to show them on the business's own site knowing the business holds no license for them (noted in data/site-content.yaml). The public portfolio copy (decision 0063) published every file in `main`'s history, so it would have redistributed them in a public repository. Taking a file out after it is published means rewriting the public history.

## Decision

- `tools/publish-portfolio.sh` leaves the paths in its `left_out_paths` list out of every commit of the public copy, in the same git filter-repo rewrite as the text replacements. The list starts with `website/public/images/vehicle-classes/`.
- A new check refuses to publish if any commit of the rewritten copy still holds a left-out path.
- The private repository keeps the pictures. The site is built from it, so it is unaffected.

## Alternatives considered

- **Publish them.** Simplest, but it redistributes pictures the business has no license for, and undoing that needs a force push to the public history.
- **Keep the pictures out of the repository.** The site is built from the repository, and the photo cards need the pictures at a fixed path, so they belong there.

## Consequences

The public copy's `data/site-content.yaml` names picture files that are not in it. Adding a path to the list after it has been published rewrites older commits, so that publish needs `--force`, as a change to the replacement rules does. Leaving out a path that was never published changes no published commit. This record adds to decision 0063; the rest of it stands.
