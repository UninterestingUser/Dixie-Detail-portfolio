# Backup runbook

Nightly backups of the PostgreSQL database: a dump on the RAID array, and an encrypted copy on Google Drive. Run every command on the server.

## What runs

`dixie-backup.timer` starts `dixie-backup.service` at 2:30 AM Eastern every night. On the night clocks spring forward, when 2:30 AM does not exist, it runs at 3:30 AM. If the server was off at that time, the backup runs as soon as it is back. The service runs `ops/backup.sh`, which:

1. Dumps the database from the running `db` container in PostgreSQL's custom format, reads the archive back to check it, and saves it as `/mnt/raid/Backups/dixie-detail/daily/dixie-detail-YYYY-MM-DD.dump`.
2. Links the first dump of each month into `monthly/dixie-detail-YYYY-MM.dump`.
3. Keeps the newest 14 daily and 12 monthly dumps, and deletes older ones.
4. Sends that night's dump with restic to `rclone:gdrive:dixie-detail-backups`, encrypted with `RESTIC_PASSWORD`. restic then applies the same 14 daily and 12 monthly policy on Drive. While there is less than 14 days of history, restic also keeps the oldest snapshot; that is expected.
5. Pings Healthchecks: a start ping, then success or failure. A failure ping carries the end of the run's log.

The service decrypts the Bitwarden token with `LoadCredentialEncrypted=`, the same way as `dixie-stack.service`. At the start of each run it fetches `RESTIC_PASSWORD`, `RCLONE_CONFIG_PASS` and `HEALTHCHECKS_BACKUP_URL`. They exist only in the script's memory and in the environment of the restic and rclone processes it starts, and are gone when the run ends.

The dumps on the RAID array are not encrypted. They are root-only (`0700` directories, `0600` files). The copy on Drive is encrypted by restic.

## First setup

Do this after the stack is running ([stack.md](stack.md)).

1. **Install the tools:** `sudo apt install restic rclone jq curl`. If the Ubuntu packages are old, use the official restic and rclone releases.

2. **Create the rclone remote as root**, with access only to the files rclone creates:

   ```bash
   sudo rclone config
   ```

   - New remote named `gdrive`, storage `drive`.
   - Scope: `drive.file` ("Access to files created by rclone only").
   - Optional but recommended: use your own OAuth client ID from the Google Cloud project, not rclone's shared one, which is rate-limited.
   - For a headless server, answer "No" to auto config and run the `rclone authorize` command it prints on Fedora, signed in to the Workspace account.
   - Back at the main menu, choose **Set configuration password**. Generate it in Bitwarden and save it as `RCLONE_CONFIG_PASS`. The config, which holds the Drive token, is then encrypted on disk at `/root/.config/rclone/rclone.conf`.

3. **Add the other secrets to Bitwarden** (project "Dixie Detail"):
   - `RESTIC_PASSWORD`: a long random value. **Without it the Drive copy cannot be read.** Bitwarden is the only place it is kept, so make sure the Bitwarden account itself has a recovery plan.
   - `HEALTHCHECKS_BACKUP_URL`: the ping URL of a new check on [healthchecks.io](https://healthchecks.io), with schedule type Cron, `30 2 * * *`, time zone `America/New_York`, and a grace time of 1 hour. If this secret is missing, backups still run without pings.

4. **Fill in the backup settings in `.env`** (see `.env.example`): `BACKUP_DIR`, `RESTIC_REPOSITORY`, `RCLONE_CONFIG`.

5. **Create the restic repository on Drive:**

   ```bash
   sudo /srv/dixie-detail/ops/restic.sh init
   ```

6. **Turn on the timer and run one backup now.** `ops/deploy.sh` installs and enables the timer; this does it by hand:

   ```bash
   sudo systemctl enable --now dixie-backup.timer
   sudo systemctl start dixie-backup.service
   journalctl -u dixie-backup.service -e
   ```

7. **Test a restore** (below). Phase 0 is done when this passes.

## Restore test

```bash
sudo /srv/dixie-detail/ops/restore-test.sh
```

The script:
- takes the newest nightly snapshot from Drive, and fails if it is more than 36 hours old
- starts a throwaway PostgreSQL container with the stack's image, no network and its data in memory
- streams the dump from restic straight into `pg_restore`, so no plaintext copy is written to disk
- checks that `pg_restore` finished without errors, that every table in the dump was restored, and that `django_migrations` exists
- prints the row count of each table

The container is removed at the end, pass or fail. Run it in Phase 0, again before launch, and after any change to the backup scripts.

## Everyday use

| Task | Command |
| --- | --- |
| Next scheduled run | `systemctl list-timers dixie-backup.timer` |
| Last run's log | `journalctl -u dixie-backup.service -e` |
| Back up now | `sudo systemctl start dixie-backup.service` |
| Snapshots on Drive | `sudo /srv/dixie-detail/ops/restic.sh snapshots` |
| Check the Drive repository | `sudo /srv/dixie-detail/ops/restic.sh check` |

## Restoring for real

1. **Pick a dump.** Normally a file in `/mnt/raid/Backups/dixie-detail`. If the RAID array is lost, take the newest from Drive with `sudo /srv/dixie-detail/ops/restic.sh dump latest /dixie-detail.dump > /root/restore.dump`, and delete that file when you are done.
2. **Stop everything but the database**, so nothing writes during the restore. Leave `dixie-stack` itself running, because the database needs its secret files:

   ```bash
   cd /srv/dixie-detail
   sudo docker compose stop app caddy cloudflared
   ```

3. **Restore over the existing database:**

   ```bash
   sudo docker compose exec -T db pg_restore --clean --if-exists -U dixie -d dixie < /path/to/the.dump
   ```

4. **Start everything again:** `sudo systemctl restart dixie-stack`, then check `/health`.
