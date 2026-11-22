---
id: 116
title: "The offline replay Worker is deployed by a script that looks its KV namespace up by name"
summary: "wrangler.toml keeps a placeholder namespace id; deploy.sh finds the namespace titled OFFLINE_REQUESTS in the Cloudflare account and deploys with a temporary copy, so no account value is committed or left behind."
date: 2026-11-21
area: website
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/guides/previewing-and-deploying-the-website.md, site/workers/offline-replay/deploy.sh, site/workers/offline-replay/wrangler.toml, tools/test-worker-deploy.sh, docs/decisions/0105-the-website-on-cloudflare-pages.md]
---

# 0116: The offline replay Worker is deployed by a script that looks its KV namespace up by name

**Status:** accepted · **Date:** 2026-11-21 · **Area:** website

## Context

The offline replay Worker (decision 0105) reads the KV namespace the Pages project binds as `OFFLINE_REQUESTS`. Wrangler takes the namespace's id only from `wrangler.toml`, so the guide told the owner to write the id there and commit it. In practice the id sat in the working copy as an uncommitted change, in the way of every branch, and committing it would put an account value into the public portfolio copy for no gain. The review asked for deploys that need no edited file.

## Decision

- **`wrangler.toml` keeps its placeholder id,** `SET_TO_THE_OFFLINE_REQUESTS_NAMESPACE_ID`, for good.
- **`site/workers/offline-replay/deploy.sh` deploys the Worker.** It lists the account's KV namespaces with wrangler, takes the one titled exactly `OFFLINE_REQUESTS` (the title `wrangler kv namespace create OFFLINE_REQUESTS` gives), writes a copy of `wrangler.toml` with that id beside the original (git ignores it), deploys with the copy and removes it, pass or fail. Its arguments are passed on to `wrangler deploy`, such as `--dry-run`.
- **It stops and deploys nothing** when wrangler isn't signed in, when no namespace or more than one has the title, when the id doesn't look like a namespace id, or when `wrangler.toml` holds anything but the placeholder.
- **`deploy.sh --id` prints the id,** for the `kv key` commands that inspect held and refused requests.
- **Tested** by `tools/test-worker-deploy.sh` with a fake wrangler, which `tools/run-tests.sh` runs.

## Alternatives considered

- **Commit the id.** It isn't a secret, but it is an account value, it would be in the public copy, and the owner's practice showed the edit stays uncommitted.
- **Wrangler's automatic resource provisioning** (leaving the id out). It can create a new namespace instead of finding the Pages project's, which would split the held requests in two.
- **The id as a setting in `.env` or Bitwarden.** One more value to keep in step, when the account already knows it.

## Consequences

Deploying is one command with no file to edit or put back. The namespace's title now matters: renaming it, or making a second `OFFLINE_REQUESTS`, stops deploys with a message saying so. The Worker's secrets are unchanged: `wrangler secret put` names the Worker only, so it still runs against `wrangler.toml`.
