---
title: Monitoring and alerts
summary: What the three Healthchecks.io checks watch, the monthly vehicle data refresh and its timer, what to do when an alert email arrives, and how to test the alerts.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-24
tags: [operations, monitoring, healthchecks, alerts, vehicles]
related: [docs/architecture/backups-and-monitoring.md, docs/operations/troubleshooting.md, docs/operations/importing-vehicle-data.md, docs/decisions/0081-monthly-vehicle-data-refresh.md, ops/vehicle-refresh.sh, data/configuration.yaml]
---

# Monitoring and alerts

Healthchecks.io sends an email to the owner's business address when a check stops pinging or reports a failure. The three checks are nightly backup, public address and vehicle data refresh; the first two are described in [../architecture/backups-and-monitoring.md](../architecture/backups-and-monitoring.md), and the vehicle data refresh below.

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

## The monthly vehicle data refresh

`dixie-vehicle-refresh.timer` starts `dixie-vehicle-refresh.service` on the first Sunday of each month at 4:15 AM Eastern, plus a random delay of up to 15 minutes, so the refresh never runs on a business day or near the 2:45 AM backup ([decision 0081](../decisions/0081-monthly-vehicle-data-refresh.md)). A refresh missed while the server was off is not made up at boot; run it by hand instead. `ops/deploy.sh` installs and enables the timer like the others.

The service runs `ops/vehicle-refresh.sh`, which runs `python manage.py refresh_vehicle_data` in a one-off app container with the download cache `/srv/dixie-vehicle-data` attached, as [importing-vehicle-data.md](importing-vehicle-data.md) runs the import by hand. That command runs `import_vehicle_data --source all --refresh`, which downloads every file again, then `classify_vehicles --refresh`. A full run makes about 3,500 vPIC calls a second apart, so it takes an hour or more.

A refresh adds new models and model years and updates facts. It never changes the vehicle class or size of a model with a model override, an approval on the approval list, or customers' jobs: those model years wait in the review queue under "Held by the monthly refresh", with the old and the new value ([../reference/vehicle-classification.md](../reference/vehicle-classification.md#the-monthly-refresh)).

The control app's home screen shows the last refresh, with its date, result and counts, next to the review queue count. Every refresh is also listed under "Vehicle data refreshes" in the Django admin, and each source's own run under "Vehicle data import runs".

## The vehicle data refresh check

| Setting in Healthchecks.io | Value |
| --- | --- |
| Name | Vehicle data refresh |
| Schedule | Cron `15 4 * * 0#1` (the first Sunday of the month at 4:15 AM), time zone America/New_York |
| Grace time | 3 hours, room for the 15-minute random delay and a slow vPIC |
| Ping address | The Bitwarden secret `HEALTHCHECKS_VEHICLE_REFRESH_URL` |

`ops/vehicle-refresh.sh` fetches `HEALTHCHECKS_VEHICLE_REFRESH_URL` from Bitwarden at the start of each run, in one call that is retried if Bitwarden answers "429 Too Many Requests", as the backup does. It pings when the run starts, then pings success or failure. The ping's first line is the refresh's one-line summary, such as "Vehicle data refresh succeeded: 12 models added, 340 changed, 7 model years sent to the review queue (3 class changes held)." A failure ping also carries the end of the run's log. Without the secret the refresh still runs, with no pings.

To set the check up: add the check in Healthchecks.io with the settings above, copy its ping address, add it to the Bitwarden project "Dixie Detail" as `HEALTHCHECKS_VEHICLE_REFRESH_URL` ([secrets-management.md](secrets-management.md)), then run a refresh by hand and confirm the check turns green.

## When the "vehicle data refresh" alert arrives

The refresh failed, or it did not finish within the grace time. Nothing a customer sees breaks: the catalog keeps the facts and classes it had, and a source that finished before the failure keeps what it wrote.

1. Read the summary at the top of the alert email, or the home screen's "Last vehicle data refresh" line. A failure names the source and the error, such as "NHTSA vPIC failed: ...".
2. Read the whole run: `journalctl -u dixie-vehicle-refresh.service --no-pager | tail -60`, and look the error up in [troubleshooting.md](troubleshooting.md).
3. A source that was down or rate-limiting (a 429 or 5xx answer that outlasted the retries, or a timeout) usually needs nothing but a second try. Run the refresh again by hand, inside `tmux` or `screen`:

   ```bash
   sudo systemctl start dixie-vehicle-refresh.service
   ```

4. "The download cache ... is missing or cannot be written": run `sudo /srv/dixie-detail/ops/deploy.sh`, which creates `/srv/dixie-vehicle-data` owned by the app container's user, or fix the owner with `sudo chown 10001:10001 /srv/dixie-vehicle-data`.
5. An error starting the container, such as a missing secret file: the stack is not running. Start it (`sudo systemctl start dixie-stack.service`) and run the refresh again.
6. When the alert says the check is late but the journal shows the run still going, vPIC is slow; wait for it to finish.

After a good run, look at the review queue for model years held by the refresh and settle each: **Accept** takes the new class, or pick the old one to keep it. For a model with a model override, change the override instead, because an override beats a queue decision.

## Testing the alerts

Stop the tunnel with `docker stop dixie-cloudflared-1`, wait about 15 minutes for the alert email, then start it again with `docker start dixie-cloudflared-1`. The check turns green on its next run and Healthchecks sends a recovery email. This was done at the end of Phase 0.
