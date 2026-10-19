---
title: Monitoring and alerts
summary: What the two Healthchecks.io checks watch, what to do when an alert email arrives, and how to test the alerts.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-18
tags: [operations, monitoring, healthchecks, alerts]
related: [docs/architecture/backups-and-monitoring.md, docs/operations/troubleshooting.md]
---

# Monitoring and alerts

Healthchecks.io sends an email to the owner's business address when a check stops pinging. The two checks are described in [../architecture/backups-and-monitoring.md](../architecture/backups-and-monitoring.md).

## When the "public address" alert arrives

The server could not reach `https://api.dixiedetail.com/health` for over 15 minutes. Work outward from the server:

1. Is the server on? Check power, and whether the APC unit shut it down (`apcaccess status` once it is back).
2. Is the home internet up?
3. Is the stack running? `systemctl status dixie-stack --no-pager` and, from `/srv/dixie-detail`, `docker compose ps`.
4. Is the tunnel connected? The Cloudflare dashboard shows the `dixie-detail` tunnel as Healthy or Down; `docker logs --tail 20 dixie-cloudflared-1` shows its side.
5. Does the app answer locally? `curl http://127.0.0.1:8000/health`.

While the server is down, the future website and its prices stay up on Cloudflare, and booking requests queue there.

## When the "nightly backup" alert arrives

The 2:45 AM backup failed or did not run. Read `journalctl -u dixie-backup.service --no-pager | tail -30` and look up the error in [troubleshooting.md](troubleshooting.md). Then run the backup by hand: `sudo systemctl start dixie-backup.service`.

## Testing the alerts

Stop the tunnel with `docker stop dixie-cloudflared-1`, wait about 15 minutes for the alert email, then start it again with `docker start dixie-cloudflared-1`. The check turns green on its next run and Healthchecks sends a recovery email. This was done at the end of Phase 0.
