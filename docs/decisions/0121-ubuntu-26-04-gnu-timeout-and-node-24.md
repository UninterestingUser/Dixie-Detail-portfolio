---
id: 121
title: "On Ubuntu 26.04 the backup uses GNU's timeout, the ops scripts are tested on 26.04, and the site moves to Node 24"
summary: "The servers run Ubuntu 26.04, whose uutils timeout kills restic at once under --signal=INT --kill-after. run_restic uses GNU's gnutimeout, CI tests the ops scripts on 26.04, and the site moves to Node 24 LTS."
date: 2026-11-22
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [ops/lib/restic.sh, tools/test-timeout.sh, tools/test-restic.sh, .github/workflows/tests.yml, data/maintenance.yaml, docs/decisions/0089-backup-rides-out-a-slow-drive.md, docs/decisions/0119-the-website-moves-to-astro-7.md, docs/operations/troubleshooting.md]
---

# 0121: On Ubuntu 26.04 the backup uses GNU's timeout, the ops scripts are tested on 26.04, and the site moves to Node 24

**Status:** accepted · **Date:** 2026-11-22 · **Area:** infrastructure

## Context

The repository said the server ran Ubuntu 24.04 and that CI was pinned to it. The current server in fact runs Ubuntu 26.04.1 LTS with kernel 7.0, and the production host will run the same release. 26.04 replaces GNU coreutils with the Rust rewrite, uutils coreutils 0.10.0. A November 2026 CI failure had already shown its `timeout` misbehaving, and the fix then was to keep CI on 24.04, on the belief that the server ran it too.

Checked on 26.04.1, uutils `timeout` gets one combination wrong: given `--signal=INT` together with `--kill-after`, it sends SIGKILL at once instead of SIGINT. Every other behavior the scripts use matches GNU's: exit status 124 when time runs out, the default TERM with or without `--kill-after`, `--signal=INT` alone, and a child's own status when it exits by itself. The backup's per-attempt cap (decision 0089) is `timeout --signal=INT --kill-after=1m 8m restic …`, the broken combination. So on the server, an attempt that reached its limit was killed before restic could remove its lock, leaving a stale lock that fails the next backup. The other uses of `timeout`, in `ops/gosu-test.sh`, use the default TERM and are unaffected.

Separately, Node 22 reaches end of life on 2027-04-30.

## Decision

- **`run_restic` uses GNU's `timeout`.** `gnu_timeout` in `ops/lib/restic.sh` picks `gnutimeout`, which 26.04 installs from the `gnu-coreutils` package (priority required, GNU coreutils 9.7), or `timeout` where that is GNU's (24.04 and Fedora). If neither is GNU's, `run_restic` refuses with a message rather than run restic under a timeout that would leave a lock.
- **`tools/test-timeout.sh`** checks the `timeout` that `run_restic` picks:
  - time running out exits 124;
  - the backup's exact form delivers SIGINT, and the child cleans up;
  - a child that ignores SIGINT is killed only after the grace period, with 137;
  - a child that exits by itself keeps its status.

  It runs in `tools/run-tests.sh`, and the owner runs it on each host. `tools/test-restic.sh` adds two cases: with only a uutils-style `timeout`, `run_restic` starts nothing; with GNU's available as `gnutimeout`, it uses that.
- **CI tests the ops scripts on 26.04.** A second Tests job, `ops-on-26-04`, runs `tools/run-tests.sh --ops-only` on GitHub's `ubuntu-26.04` runner and prints which `timeout` it has. The app's tests keep running in the production image, on the `ubuntu-24.04` runner whose image has Podman. The Docs and Site workflows stay pinned to 24.04, which doesn't affect the servers.
- **Node 24 LTS for the site and the Worker's tooling:** `site/.nvmrc` 24, `engines` `>=24`, the Pages setting `NODE_VERSION` 24. Under Node 24.22.3 the Astro build has no warnings, the price check and the 21 unit tests (including the Worker's) pass, and Wrangler bundles the Worker. CI runs the browser and Lighthouse tests on 24.

## Alternatives considered

- **Install `coreutils-from-gnu` to make GNU's the system `timeout`.** It changes every coreutils command on the host, for one script's sake, and a release upgrade could quietly undo it. Naming `gnutimeout` keeps the change in the one place that needs it, and the test notices if it goes.
- **Drop `--kill-after`, since `--signal=INT` alone works under uutils.** Then a restic that ignored SIGINT would never be stopped, and the attempt cap would no longer cap anything.
- **Run all of CI on 26.04.** The app tests need Podman on the runner, and the Docs and Site checks don't touch the servers. Only the ops scripts run on the servers' release, so only they need testing there.

## Consequences

The backup's time limit again lets restic remove its lock on the servers. A future Ubuntu release is checked with `tools/test-timeout.sh` before it is trusted. Node's next planned upgrade is due before 2028-04-30.
