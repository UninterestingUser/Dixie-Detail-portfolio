# Server setup

The home server: hostname "Server", LAN address 192.0.2.10, Ubuntu Server with Docker.

| Part | Detail |
| --- | --- |
| CPU | AMD Ryzen 5 5600, 6 cores / 12 threads |
| RAM | 16 GB DDR4 |
| Boot drive | Samsung 970 EVO Plus 500 GB NVMe (database lives here) |
| Data | Four 4 TB disks in mdadm RAID 5 at `/mnt/raid` (backups land here) |
| Power | APC battery covering the server, firewall and modem |

## 1. Tailscale node

The server joins the tailnet as its own device, in addition to the pfSense subnet route. Your LAN uses 192.168.1.x, a very common home range, so a Wi-Fi network using the same range can block the pfSense route. A direct node avoids that and gives the control app a proper HTTPS address.

**Install and join.** The second command prints a link; open it on any signed-in device to approve the server.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Do not add `--accept-routes`. It is off by default on Linux and must stay off, because the server already sits on the network pfSense advertises.

**Stop the key expiring.** In the admin console, open Machines, find the server, and choose "Disable key expiry".

**Turn on names and HTTPS.** On the admin console's DNS page, enable MagicDNS, then "Enable HTTPS" under HTTPS Certificates. Machine names appear on a public certificate ledger; "Server" reveals nothing.

**Check it.**

```bash
tailscale status
tailscale ip -4
```

**Publish the control app (Phase 0, once the app runs).** Port 8000 is a placeholder.

```bash
sudo tailscale serve --bg 8000
tailscale serve status
```

The app listens on loopback only, so it is not exposed on the LAN or the internet.

## 2. Clean shutdown on battery

Connect the APC unit's USB cable to the server and install `apcupsd`, so the server shuts itself down before the battery runs out.

## 3. Backups

- Nightly database dumps at 2:30 AM Eastern to `/mnt/raid/Backups/dixie-detail`, keeping 14 daily and 12 monthly.
- An encrypted restic copy in the owner's Google Workspace Drive (`gdrive:dixie-detail-backups`), through rclone with access only to the files it creates, under the same 14 daily and 12 monthly policy.
- The restic password and rclone's config password come from Bitwarden only while the backup runs.
- Healthchecks is pinged on success and failure.
- A test restore in Phase 0 and again before launch, with `ops/restore-test.sh`.

Setup and restore steps are in the [backup runbook](backups.md).

## 4. Secrets

The server keeps one secret, the Bitwarden machine-account token, encrypted with `systemd-creds` and bound to the TPM chip where available. Everything else comes from Bitwarden Secrets Manager when a service starts. The deploy key also lives in Bitwarden and is loaded into `ssh-agent` only for a pull. Step-by-step setup is in the [Phase 0 stack runbook](stack.md).

## Sources

- Tailscale: [Linux install](https://tailscale.com/docs/install/linux), [enabling HTTPS](https://tailscale.com/kb/1153/tailscale-cert), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [overlapping subnet routes](https://tailscale.com/docs/reference/troubleshooting/network-configuration/lan-traffic-overlapping-subnets)
- The key-expiry menu and the `--bg` flag are from general knowledge; confirm them in the current Tailscale console and `tailscale serve --help`.
