---
id: 122
title: "The maintenance assistant reviews every Dependabot pull request, and after launch may merge minor, patch and security updates whose checks have all passed"
summary: "Until launch the owner merges every Dependabot pull request. After launch the assistant may merge passing minor, patch and security updates; majors, wider changes and deploys stay with the owner."
date: 2026-11-22
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [docs/decisions/0118-dependabot-and-a-maintenance-list.md, docs/architecture/keeping-components-current.md, data/maintenance.yaml, .github/dependabot.yml]
---

# 0122: The maintenance assistant reviews every Dependabot pull request, and after launch may merge minor, patch and security updates whose checks have all passed

**Status:** accepted · **Date:** 2026-11-22 · **Area:** infrastructure

## Context

Dependabot's weekly pull requests (decision 0118) arrived as planned. Most were routine and passed every check, but some needed judgment. #79 and #80 tried a two-major Astro jump that failed the build. #90 tried a Python upgrade in only one Dockerfile. #93 was a gunicorn major whose start options had to be checked by hand. Merging each one by hand is a weekly chore, and reading each one carefully is what catches the bad ones.

## Decision

- **The maintenance assistant reviews each Dependabot pull request as it opens.** It reads what changed upstream, whether the update is minor, patch, security or major, whether it touches more than dependency files, and every check's result. Then it tells the owner what to do with it.
- **Until launch,** the owner merges every Dependabot pull request.
- **After launch,** the assistant may merge a Dependabot **minor, patch or security update** once **every check has passed**.
- **Always the owner's:** a **major update**, a pull request that **changes more than dependency files**, and **every deploy**. Dependency files are the requirements files, the site's `package.json` and lock file, the image tags in `compose.yaml` and the Dockerfiles, and the actions' versions in the workflows. A merged update that changes the server waits for the owner's deploy.
- **The GitHub setting.** "Require status checks to pass" on `main` (a branch protection rule or ruleset) would make GitHub enforce the last condition. On a private repository it needs a paid plan, and this account's plan refuses it. The rule stands without it: the assistant merges only after reading every check as passed, never with one pending or failed. If the plan changes, the owner turns the setting on.

## Alternatives considered

- **GitHub's auto-merge for Dependabot.** It also needs the required-checks setting, so it isn't available, and it would merge without anyone reading the change.
- **The owner merges everything forever.** Safe, but the routine merges crowd out the ones that need the owner's attention.

## Consequences

After launch, routine updates go in without waiting for the owner, and the owner's time goes to majors, unusual pull requests and deploys. The maintenance list and its doc describe the same rule.
