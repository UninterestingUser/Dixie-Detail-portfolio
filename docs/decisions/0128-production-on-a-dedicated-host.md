---
id: 128
title: "Production on a dedicated host, with its own firewall, a shared UPS, a monitor account and a closed tailnet tag"
summary: "Production runs on its own host with a ufw firewall, the UPS shared over apcupsd, a forced-command monitor account, a tailnet tag that starts no connections, and .env kept in Bitwarden."
date: 2026-11-22
area: infrastructure
status: accepted
audience: [owner, developer]
visibility: internal
updated: 2026-11-22
supersedes: []
superseded_by: []
related: [docs/decisions/0127-hourly-backups-to-the-backup-host-and-nightly-to-backblaze.md, docs/decisions/0125-the-stack-restarts-itself-deploys-in-place-and-the-tunnel-reaches-only-caddy.md, docs/operations/building-the-production-host.md, docs/operations/moving-production.md, docs/operations/tailscale-policy.md, docs/operations/when-its-down.md, ops/host-firewall.sh, ops/ups/, ops/monitor/, ops/lib/deploy.sh, docs/architecture/server-and-stack.md, docs/architecture/network-and-access.md]
---

# 0128: Production on a dedicated host, with its own firewall, a shared UPS, a monitor account and a closed tailnet tag

**Status:** accepted · **Date:** 2026-11-22 · **Area:** infrastructure

## Context

The stack ran on a server that also runs unrelated software, which shared its root, its network and its disks with the business (review finding H3). The owner has a dedicated mini PC for production (2 cores, 16 GB, a 512 GB NVMe drive, Intel PTT), on its own pfSense network. The current server becomes the backup host (decision 0127). One UPS feeds both, by one USB cable. The owner's maintenance assistant needs to read the production host's state without being able to change anything.

## Decision

- **A dedicated production host** runs only the stack, on the same Ubuntu Server LTS release as the backup host (26.04). It is built from a blank machine with only Bitwarden, the backups and this repository (docs/operations/building-the-production-host.md).
- **Disk encryption only if it unlocks itself.** The production host uses full-disk encryption only if its Ubuntu release offers TPM-backed encryption that unlocks with no passphrase, proven by a cold reboot; otherwise none, and the build guide records which. A passphrase at boot would keep the site down after every power cut until the owner typed it.
- **The host's own firewall** (`ops/host-firewall.sh`, ufw): SSH only over Tailscale, the control app's `tailscale serve` port over Tailscale, apcupsd's port 3551 only from `BACKUP_HOST_ADDRESS`, nothing else in. pfSense limits the production network's traffic to the backup server's port and the internet.
- **The tailnet policy.** The owner's devices can reach everything; the production host is tagged `tag:dixie-prod`, doesn't accept routes, and can start no connection into the tailnet. The policy and its tests are in docs/operations/tailscale-policy.md. The backups therefore go over the LAN, through pfSense.
- **The UPS on two hosts** (`ops/ups/`): the production host has the USB cable and runs apcupsd as the network server on port 3551. It shuts down at 20% charge or about 5 minutes of runtime left, and its shutdown tells the UPS to switch its outlets off (Ubuntu's `apcupsd_shutdown` hook runs `apccontrol killpower`; checked in Ubuntu 26.04's apcupsd 3.14.14-7, and by the Tests workflow on 26.04), so both hosts power back on when mains power returns, their firmware set to power on after a power loss. The backup host is a network client that shuts down after 2 minutes on battery. The UPS's own shutdown delay must leave both hosts time to finish shutting down; the build guide has the check.
- **A `monitor` account** for the owner's maintenance assistant (`ops/monitor/`): an SSH key only, no password, no sudo, not in the docker group, and a forced command (`command=` in a root-owned `authorized_keys`, and `ForceCommand` in sshd) that prints a status report and nothing else: release and kernel, pending updates, reboot required, disk use, NVMe health, failed units, last backup runs, and container health. A root timer (`dixie-monitor-snapshot.timer`) writes the container and NVMe part to a file the account can read, so it never needs Docker or sudo.
- **`.env` in Bitwarden.** The secret `DOT_ENV` holds a copy of the production host's `.env`; the build guide creates `.env` from it, and every deploy compares the two and warns, naming the settings (never their values) that differ.

## Alternatives considered

- **Keep production on the current server.** Rejected by the review: unrelated software shares its root.
- **A passphrase for disk encryption.** Rejected: the site would stay down after every power cut until someone typed it.
- **nftables rules of our own instead of ufw.** ufw is Ubuntu's standard and is enough for three rules; the tunnel network keeps its own iptables chains (decision 0125).
- **A monitor account with sudo for a few commands.** A forced command can't be talked into anything else; sudo rules can be.

## Consequences

- The backup host and the production host must both be up for the hourly backups; Healthchecks says when they aren't.
- The production host can't reach the owner's devices over the tailnet, by design; anything it needs from the backup host goes over the LAN.
- A firmware update or TPM reset on the production host locks its credentials; the build guide covers encrypting them again.
