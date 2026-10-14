---
title: Deploying changes to the server
summary: The routine for getting a merged pull request onto the server, and what to restart, copy or add afterwards depending on what changed.
audience: [owner, developer]
visibility: restricted
status: current
updated: 2026-10-13
tags: [operations, deploy, git, systemd]
related: [docs/architecture/server-and-stack.md, docs/architecture/secrets.md, docs/operations/troubleshooting.md, docs/reference/configuration.md]
---

# Deploying changes to the server

Code is written on the Fedora workstation (usually by Claude Code), reviewed and merged as a pull request on GitHub, then pulled by the server into `/srv/dixie-detail`. The server never writes to the repository.

## Step 1: Merge the pull request

Read the pull request description first. Note any new settings, secret names, or `.service` and `.timer` files it mentions. Then merge it on GitHub.

## Step 2: Pull on the server

`ops/deploy.sh` does the pull and steps 5 and 6 in one go:

```bash
sudo /srv/dixie-detail/ops/deploy.sh
```

It loads the deploy key `DEPLOY_SSH_KEY` from Bitwarden into a private `ssh-agent`, pulls `DEPLOY_BRANCH` from `DEPLOY_REMOTE` (both in `.env`) with fast-forward only, and stops the agent. It then installs any new or changed `.service` and `.timer` files from `ops/`, enables `dixie-stack.service`, `dixie-backup.timer` and `dixie-public-health.timer`, rebuilds the app image and restarts the stack. It needs `BWS_PROJECT_ID`, `BWS_SERVER_URL`, `DEPLOY_REMOTE` and `DEPLOY_BRANCH` in `.env`. Phase 0 did not use it; check its first run closely.

**By hand.** Phase 0 pulled with these commands, run one line at a time. The first line asks for your password; if you paste several lines at once, the password prompt swallows them.

```bash
export BWS_ACCESS_TOKEN="$(sudo systemd-creds decrypt --name=bws-token /etc/credstore.encrypted/dixie-bws-token.cred -)"
eval "$(ssh-agent -s)"
bws secret list | jq -r '.[] | select(.key=="DEPLOY_SSH_KEY") | .value' | ssh-add -
git -C /srv/dixie-detail pull
ssh-agent -k
unset BWS_ACCESS_TOKEN
```

Expect `Identity added: (stdin) (Server deploy key)` followed by the list of changed files. After a pull by hand, do steps 5 and 6 yourself.

## Step 3: Add any new settings to .env

New features often add settings to `.env.example` that the server's `.env` does not have yet. List the missing ones:

```bash
cd /srv/dixie-detail
diff <(grep -oE '^[A-Z_]+=' .env.example | sort) <(grep -oE '^[A-Z_]+=' .env | sort)
```

Lines starting with `<` are missing from `.env`. Add them with `nano .env`. Remember the format rules: `DJANGO_ALLOWED_HOSTS` takes bare host names separated by commas, with no `https://`.

## Step 4: Add any new secrets to Bitwarden

If the pull request names new secrets, create them in the Bitwarden web app, in the Dixie Detail project, with exactly the names the code uses. To list every secret name the scripts ask for:

```bash
grep -ohE 'bws_(optional_)?value "\$json" [A-Z][A-Z0-9_]+|^put [^ ]+ +[A-Z][A-Z0-9_]+' /srv/dixie-detail/ops/*.sh /srv/dixie-detail/ops/lib/*.sh | awk '{print $NF}' | sort -u
```

## Step 5: Install new or changed systemd units

The server runs installed copies of the unit files in `/etc/systemd/system/`, not the files in the repository. `ops/deploy.sh` installs them itself. After a pull by hand that adds or changes a unit:

```bash
cd /srv/dixie-detail
find ops -name "*.service" -o -name "*.timer"
sudo cp ops/NAME.service ops/NAME.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now NAME.timer
systemctl list-timers | grep -i dixie
```

A timer cannot start unless its matching `.service` file is installed too.

## Step 6: Restart what changed

| What changed | Run |
| --- | --- |
| App code, `compose.yaml`, `ops/stack-start.sh`, `.env` or a stack secret | `sudo systemctl restart dixie-stack` |
| `ops/dixie-stack.service` itself | Copy it again (step 5), then `sudo systemctl daemon-reload` and `sudo systemctl restart dixie-stack` |
| The backup or health-check scripts | Nothing; the next timer run uses the new script. Run the service by hand to test it |
| Docs only | Nothing |

## Step 7: Check it works

```bash
systemctl status dixie-stack --no-pager
cd /srv/dixie-detail && docker compose ps
curl http://127.0.0.1:8000/health
curl -sS https://api.dixiedetail.com/health
```

All containers should be up, and both health checks should answer rather than return "Bad Request (400)".

After a change to `compose.yaml`, the Caddyfile or the start script, also check that the doors and secrets are still closed:

```bash
sudo ss -tlnp | grep -E ':8000|:8080'
sudo docker inspect dixie-app-1 --format '{{json .Config.Env}}'
```

The first should show only `127.0.0.1:8000`. The second should show file paths such as `POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password`, never a secret value. If anything fails, see [troubleshooting.md](troubleshooting.md).
