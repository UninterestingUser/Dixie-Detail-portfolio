---
id: 111
title: "The public portfolio copy is built from an include list, without operations docs or restricted files"
summary: "tools/publish-portfolio.sh publishes only the paths in data/portfolio-include.txt, never docs/operations/ or a file marked visibility: restricted, and filters the whole history to them before the text replacements run."
date: 2026-11-21
area: repository
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-21
supersedes: []
superseded_by: []
related: [docs/decisions/0063-public-portfolio-copy.md, docs/decisions/0104-portfolio-copy-leaves-out-unlicensed-pictures.md, docs/operations/publishing-the-portfolio.md, tools/publish-portfolio.sh, tools/portfolio_paths.py, tools/test-portfolio.sh, data/portfolio-include.txt]
---

# 0111: The public portfolio copy is built from an include list, without operations docs or restricted files

**Status:** accepted · **Date:** 2026-11-21 · **Area:** repository

## Context

The public copy (decision 0063) published every file in `main`'s history and relied on text replacements to hide private details, with a short list of left-out paths (decision 0104). A review (finding M4) pointed out that this is a blocklist: every new file is public by default, the documents marked `visibility: restricted` and the operations runbooks were published in full with only their addresses replaced, and a private detail the replacement rules do not know about goes out with them.

## Decision

- `tools/publish-portfolio.sh` builds the public copy from an allowlist, `data/portfolio-include.txt`, kept in the repository. It names paths only: folders (trailing `/`) and single files, no wildcards, in an `[include]` and an `[exclude]` section.
- Always left out, even inside an included folder: everything under `docs/operations/`, every file whose header says `visibility: restricted`, and everything in the `[exclude]` section. The list and the headers are read at the commit being published.
- The whole history is filtered to the chosen paths with git filter-repo, so a left-out file is in no public commit. The choice covers every path in the history that passes the rules, not only the files in `main`, so renaming or deleting a file later does not rewrite earlier public commits. A file no longer in `main` that was restricted in any commit is left out.
- The text replacements and the mailmap run afterward, in a second pass, as a second layer.
- New checks before pushing: every path in every commit is on the include list and not on its exclude list, none is under `docs/operations/`, and no version of any file is marked restricted. A file that is internal in `main` but was restricted earlier stops the publish until it goes on the exclude list, because its older versions would be published.
- The script prints the files included, each file left out by rule and why, and the commits kept.
- `tools/test-portfolio.sh`, run by `tools/run-tests.sh`, tests the rules and the checks against throwaway repositories. GitHub Actions installs git filter-repo for it.
- The left-out paths of decision 0104 move from the script to the exclude section.

## Alternatives considered

- **Keep the blocklist and add restricted files to it.** Every new folder or file would still be public until someone remembered to block it.
- **Filter the history to the exact files in `main`.** Simpler, but every rename or deletion would remove a path from older commits, so nearly every publish would need a force push.
- **Publish a snapshot of `main` without history.** Leaves out restricted files easily, but loses the commit history, which decision 0063 keeps on purpose.
- **Mark public files in their own headers.** Code and data files have no header block, and the list in one file is easier to review.

## Consequences

- The first publish after this changes commits that are already public, so it needs `--force`. Recreating the public repository is the cleanest way to drop the old commits from GitHub, since a force push leaves them reachable by hash for a while; `docs/operations/publishing-the-portfolio.md` has both.
- A new top-level folder, docs folder or loose file is not published until it is added to the include list.
- Some published docs, the decision index among them, link to restricted docs or to `docs/operations/`. Those links lead nowhere in the public copy.
- Making a restricted file internal later does not publish it: it must be added to the exclude list, or published under a new name.
- Older commits keep the website under `website/`, which is on the include list for that reason.
- This record adds to decisions 0063 and 0104; the rest of them stands.
