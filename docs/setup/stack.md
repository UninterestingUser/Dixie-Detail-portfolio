# Phase 0 stack runbook

The Docker stack on "Server": PostgreSQL, the Django core app, Caddy and cloudflared. Run every command on the server.

## How it fits together

| Service | Reachable from | Notes |
| --- | --- | --- |
| Caddy, port 8000 | `127.0.0.1:8000` on the server only | The whole app. `tailscale serve` publishes it to the tailnet. Refuses requests from cloudflared. |
| Caddy, port 8080 | The `tunnel` Docker network only | `/health` and `/api/public/` only; everything else is a 404. The app checks the same rule. |
| cloudflared | Outbound to Cloudflare | Sends tunnel traffic to `http://caddy:8080`. Cannot reach the app or database directly. |
| app (Django) | The `backend` Docker network | `/health` reports whether the app can reach the database. |
| db (PostgreSQL 18) | The `backend` Docker network | Data in the `dixie_pgdata` volume, on the NVMe drive. |

No other port is published.

## Secrets

Secrets live only in Bitwarden Secrets Manager, project "Dixie Detail". The names are listed in [.env.example](../../.env.example).

1. `dixie-stack.service` decrypts the Bitwarden machine-account token from `/etc/credstore.encrypted/dixie-bws-token.cred` into its private, in-memory credentials directory.
2. `ops/stack-start.sh` fetches the project's secrets with `bws`, with its state file turned off. It writes each secret to `/run/dixie-stack/secrets` (tmpfs, root-only), owned by the user of the one container that needs it.
3. Compose mounts each file into its container at `/run/secrets/<name>`. Containers get file paths in their environment, never values.
4. When the service stops, systemd deletes `/run/dixie-stack`.

`ops/deploy.sh` decrypts the same token with `systemd-creds`, fetches `DEPLOY_SSH_KEY`, and loads it into a private `ssh-agent` for five minutes at most. It kills the agent as soon as the pull finishes.

## First install

1. **Install the tools.** Docker Engine with the Compose plugin, `jq`, and `bws` (the [Bitwarden Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli/)) on the `PATH` for root.

2. **Create the secrets in Bitwarden**, in the "Dixie Detail" project, with the names in `.env.example`:
   - `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY`: long random values. Use Bitwarden's generator.
   - `CLOUDFLARE_TUNNEL_TOKEN`: see step 6.
   - `DEPLOY_SSH_KEY`: generate an ed25519 key on Fedora, paste the private key into Bitwarden, add the public key to the GitHub repository as a read-only deploy key, then delete both files.

3. **Store the machine-account token.** It is never echoed or written in plaintext. The default `--with-key=auto` binds it to the TPM when the server has one.

   ```bash
   sudo install -d -m 0700 /etc/credstore.encrypted
   read -rsp 'Bitwarden machine-account token: ' t; echo
   printf '%s' "$t" | sudo systemd-creds encrypt --name=bws-token - /etc/credstore.encrypted/dixie-bws-token.cred
   unset t
   ```

4. **Write the settings.** From a checkout on Fedora, copy `ops/` and `.env.example` to the server. Then:

   ```bash
   sudo install -d -m 0755 /opt/dixie-detail
   sudo cp .env.example /opt/dixie-detail/.env
   sudoedit /opt/dixie-detail/.env
   ```

5. **Pull and start.** The first run fills `/opt/dixie-detail` from GitHub, installs and enables `dixie-stack.service`, builds the app and starts the stack.

   ```bash
   sudo DIXIE_DIR=/opt/dixie-detail bash ops/deploy.sh
   ```

   Afterwards, delete the copied `ops/` and `.env.example` from your home directory.

6. **Tunnel route.** In the Cloudflare dashboard (Zero Trust, Networks, Tunnels), create a tunnel and copy its token into `CLOUDFLARE_TUNNEL_TOKEN`. Add one public hostname, for example `api.dixiedetail.com`, with service `http://caddy:8080`. Never point it at port 8000.

7. **Publish to the tailnet:** `sudo tailscale serve --bg 8000` (see [server.md](server.md#1-tailscale-node)).

## Everyday use

| Task | Command |
| --- | --- |
| Deploy the latest `main` | `sudo /opt/dixie-detail/ops/deploy.sh` |
| Restart (fetches secrets again) | `sudo systemctl restart dixie-stack` |
| Status and logs | `systemctl status dixie-stack`, `cd /opt/dixie-detail && sudo docker compose logs -f` |
| Health over the tailnet | `curl https://server.<tailnet>.ts.net/health` |
| Health through the tunnel | `curl https://api.dixiedetail.com/health` |

Start and stop the stack with `systemctl`, not `docker compose up`. Compose on its own has no secrets to mount.

## Rotating a secret

Change it in Bitwarden, then `sudo systemctl restart dixie-stack`. One exception: PostgreSQL reads `POSTGRES_PASSWORD` only when it first creates the database. To change it, first set the new password in the database with `sudo docker compose exec db psql -U dixie -d dixie -c '\password dixie'`, which prompts for it and keeps it out of the shell history. Then update Bitwarden and restart.

## Checks

- `sudo ss -tlnp | grep -E ':8000|:8080'` shows only `127.0.0.1:8000`.
- `curl -i https://api.dixiedetail.com/anything` returns 404 from Caddy.
- `sudo docker inspect dixie-app-1 --format '{{json .Config.Env}}'` shows file paths, not values.
