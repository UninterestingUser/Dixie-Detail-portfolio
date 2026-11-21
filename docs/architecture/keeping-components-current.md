---
title: Keeping components current
summary: How the system's components are kept up to date - Dependabot's weekly pull requests, the planned major upgrades, and the maintenance list of pins and end-of-life dates.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-11-21
tags: [maintenance, dependencies, dependabot, upgrades]
related: [data/maintenance.yaml, .github/dependabot.yml, docs/decisions/0118-dependabot-and-a-maintenance-list.md, docs/decisions/0117-hardened-containers-and-the-database-without-gosu.md, docs/operations/deploying-changes.md, docs/operations/updating-the-kernel.md]
---

# Keeping components current

Every version the system runs on is pinned, so nothing changes under it by surprise. Keeping those pins current is split three ways: Dependabot proposes the updates it can read, the owner's Grok Bot watches for news about the rest, and the owner plans the major upgrades. The facts per component are in [data/maintenance.yaml](../../data/maintenance.yaml); this page explains how to use them (decision 0118).

## The maintenance list

[data/maintenance.yaml](../../data/maintenance.yaml) has one entry per component: the pinned version, where it is pinned, the upstream end-of-life date, who watches it, and how to update and test it. It covers the server (the Ubuntu release, the kernel, Docker, apcupsd, the NUC's firmware), the stack (PostgreSQL, Python, Django, gunicorn, Pillow and libheif, Caddy, cloudflared), the backups and secrets (restic, rclone, the bws CLI), the network (Tailscale), the website (Node on Cloudflare Pages, Astro, the replay Worker's compatibility date, Wrangler) and the Google Maps APIs in use.

For what Dependabot watches, the list names the version line, such as Django 5.2 LTS or PostgreSQL 18, and the exact version is in the file it names, which Dependabot keeps current. A pull request that changes a line, or any pin Dependabot doesn't watch, updates the list in the same pull request. An end-of-life date within a year is a planned upgrade for the roadmap.

## Dependabot's weekly pull requests

`.github/dependabot.yml` checks five ecosystems every Monday at 6 AM Eastern: pip for the app, npm for the website, the app's base image in `app/Dockerfile` and `app/Dockerfile.test`, the image tags in `compose.yaml`, and the GitHub Actions in the workflows.

- **Minor and patch updates** for each ecosystem come together in one pull request, such as "pip-minor-and-patch".
- **A major update** of anything else comes as its own pull request, so it can be read on its own.
- **Security updates** come as they're published, each on its own. They need Dependabot security updates switched on in the repository's settings (Code security).
- **Every pull request runs CI** like any other: the Tests workflow (`tools/run-tests.sh`) on all of them, and the Site workflow when `site/` changes. Merge once the checks pass.

### Updates that reach the server

Merging an update to `app/requirements.txt`, the Dockerfiles or `compose.yaml` changes nothing on the server until it is deployed ([deploying-changes.md](../operations/deploying-changes.md)). After deploying an image update, check what its entry in the maintenance list says to test, such as the public health check after a cloudflared update. A website update reaches the site through Cloudflare's build of `main`, as any merge does.

## Planned major upgrades

Dependabot never proposes a major version of Django, PostgreSQL, Python or Node. Each is a piece of work with its own plan:

- **PostgreSQL** moves to a new major version by a dump and restore into a new volume, never by changing the image tag on the old one, which the new version can't read.
- **Python** moves in both Dockerfiles together; Dependabot sends its patch releases only.
- **Django** moves from one LTS release to the next.
- **Node** moves in `site/.nvmrc`, the `engines` line in `site/package.json` and the Pages build setting `NODE_VERSION` together.

## What Dependabot can't see

The server's packages (the Ubuntu release, the kernel, Docker, restic, rclone, Tailscale, apcupsd), the bws CLI, Node on Pages, Wrangler, the Worker's compatibility date and the Google Maps APIs are not in any file Dependabot reads. Their entries in the maintenance list name who watches them. Ubuntu's security updates install themselves on the server with `unattended-upgrades`. A new kernel is tested before it becomes the default ([updating-the-kernel.md](../operations/updating-the-kernel.md)).
