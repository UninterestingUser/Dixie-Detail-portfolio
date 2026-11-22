---
id: 118
title: "Dependabot sends weekly grouped updates, and a maintenance list tracks every component"
summary: "Weekly Monday pull requests group each ecosystem's minor and patch updates, majors of Django, PostgreSQL, Python and Node are planned by hand, and data/maintenance.yaml lists each component's pin and end of life."
date: 2026-11-21
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [.github/dependabot.yml, data/maintenance.yaml, docs/architecture/keeping-components-current.md, tools/run-tests.sh]
---

# 0118: Dependabot sends weekly grouped updates, and a maintenance list tracks every component

**Status:** accepted · **Date:** 2026-11-21 · **Area:** infrastructure

## Context

A review (finding L6) found every version pinned, which is good, but nothing watching the pins: no update pull requests, and no single place saying where each version is pinned, when upstream stops supporting it, or how to test a change. Several components (the Ubuntu release, Node on Pages, restic, the bws CLI) aren't in any file a bot can read.

## Decision

- **`.github/dependabot.yml`** covers pip (`app/`), npm (`site/`), Docker (the app's base image in both Dockerfiles), Docker Compose (the image tags in `compose.yaml`) and GitHub Actions. Every Monday at 6 AM Eastern, each ecosystem's minor and patch updates come as one pull request; a major update of anything else comes on its own.
- **No major version bumps for Django, PostgreSQL, Python or Node.** They are planned upgrades. Django and PostgreSQL majors are ignored. The Python image is held to patch releases, since 3.13 to 3.14 counts as a minor version to Dependabot but is a planned upgrade. Node's version is in `site/.nvmrc` and the Pages setting `NODE_VERSION`, which Dependabot doesn't read.
- **Security updates** come as they're published, one pull request each, outside the weekly groups. They are switched on in the repository's settings.
- **CI.** Every Dependabot pull request runs the same workflows as any other: Tests on all of them, Site when `site/` changes, Docs when the docs workflow changes. `tools/run-tests.sh` now also fails when `app/Dockerfile` and `app/Dockerfile.test` name different base images.
- **`data/maintenance.yaml`** lists every component with its pinned version, where it is pinned, the upstream end-of-life date, who watches it (Dependabot, Grok Bot or the owner) and how to update and test it, explained in [keeping-components-current.md](../architecture/keeping-components-current.md). It holds facts only, no server values.

## Alternatives considered

- **Renovate.** More flexible, but another app with access to the repository, when Dependabot is built into GitHub.
- **Daily or ungrouped updates.** Many small pull requests a week, each a CI run and a merge, for a one-owner business.
- **Let Dependabot propose majors of the four.** Each needs its own plan (a database dump and restore, a Python or Node move across workflows, images and Pages), not a version bump.

## Consequences

The owner merges a few pull requests on Mondays, after their checks pass. The maintenance list names version lines (Django 5.2, PostgreSQL 18) for what Dependabot watches, so its weekly pull requests leave the list true; a pull request that changes a line updates the list too. End-of-life dates come with the list, so planned upgrades can be put on the roadmap ahead of time. `.github/dependabot.yml` stays out of the public portfolio copy (`data/portfolio-include.txt`): there it would open update pull requests against a repository that each publish rewrites.
