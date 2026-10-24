---
title: Managing secrets
summary: Step-by-step procedures for adding, renaming and rotating secrets, re-encrypting the server's Bitwarden token, and replacing the deploy key.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-23
tags: [operations, secrets, bitwarden, security]
related: [docs/architecture/secrets.md, data/configuration.yaml, docs/reference/configuration.md]
---

# Managing secrets

The design is in [../architecture/secrets.md](../architecture/secrets.md), and every secret's name is in [data/configuration.yaml](../../data/configuration.yaml). Never paste a secret value into a chat, an issue, a commit, a doc or a file.

## Add a new secret

1. In the Bitwarden web app, open Secrets Manager › Projects › Dixie Detail and add a secret. Use the exact name the code asks for, capitals included. Use Bitwarden's generator for passwords.
2. Make sure `data/configuration.yaml` and `.env.example` list the name (the pull request that introduced it should have done this).
3. Restart whatever uses it, usually `sudo systemctl restart dixie-stack`.

## Rename a secret

Rename it in the Bitwarden web app; the value is kept. A name the code asks for that does not exist stops the stack with "Bitwarden secret NAME: expected 1, found 0".

## Rotate a secret

1. Generate the new value in Bitwarden and save it over the old one.
2. Restart the service that uses it.
3. Some secrets also live elsewhere and must change there too: `POSTGRES_PASSWORD` must be changed inside PostgreSQL as well, before the restart (plan this; PostgreSQL reads the secret only when it first creates the database, so changing only Bitwarden locks the app out). Set the new password with `cd /srv/dixie-detail && sudo docker compose exec db psql -U dixie -d dixie -c '\password dixie'`, which prompts for it and keeps it out of the shell history; `CLOUDFLARE_TUNNEL_TOKEN` is reissued in the Cloudflare dashboard, and Healthchecks ping URLs change if a check is recreated.
4. Never rotate `RESTIC_PASSWORD` casually: existing snapshots stay locked to the old password. If it must change, add a new key to the restic repository first (`restic key add`), then update all three copies (Secrets Manager, the Bitwarden vault, the sealed paper copy).

## Check which secrets the server can see

Names only, no values:

```bash
export BWS_ACCESS_TOKEN="$(sudo systemd-creds decrypt --name=bws-token /etc/credstore.encrypted/dixie-bws-token.cred -)"
bws secret list | jq -r '.[].key' | sort
unset BWS_ACCESS_TOKEN
```

## Re-encrypt or replace the server's Bitwarden token

Needed if the machine-account token is rotated, the TPM is reset, or the server is rebuilt. In Bitwarden, create a new access token for machine account `server` (label it `dixie-server`), then on the server run these lines one at a time. After `read -rs BWS_TOKEN` the cursor waits: paste the token and press Enter.

```bash
sudo mkdir -p /etc/credstore.encrypted
read -rs BWS_TOKEN
printf '%s' "$BWS_TOKEN" | sudo systemd-creds encrypt --with-key=host+tpm2 --name=bws-token - /etc/credstore.encrypted/dixie-bws-token.cred
unset BWS_TOKEN
sudo systemd-creds decrypt --name=bws-token /etc/credstore.encrypted/dixie-bws-token.cred - | wc -c
```

The last line prints the token's length without showing it. `--with-key=host+tpm2` makes the command fail rather than silently skip the TPM. `systemd-analyze has-tpm2` must say `yes`; if it says `partial`, install `libtss2-rc0t64`. Revoke the old token in Bitwarden afterwards.

## Replace the deploy key

```bash
ssh-keygen -t ed25519 -f /dev/shm/dixie_deploy -N "" -C "Server deploy key"
cat /dev/shm/dixie_deploy.pub
cat /dev/shm/dixie_deploy
```

Add the `.pub` line in GitHub under the repository's Settings › Deploy keys with "Allow write access" off, and delete the old key there. Save the private key, every line, over the `DEPLOY_SSH_KEY` secret in Bitwarden. Then `rm /dev/shm/dixie_deploy /dev/shm/dixie_deploy.pub`.
