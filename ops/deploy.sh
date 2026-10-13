#!/usr/bin/env bash
# Pulls the latest code with the deploy key, then rebuilds and restarts the
# stack. Run on the server as root:
#
#   sudo /srv/dixie-detail/ops/deploy.sh
#
# The deploy key comes from Bitwarden and lives only in a private ssh-agent
# for the length of the pull. First install: see docs/setup/stack.md.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
CRED=/etc/credstore.encrypted/dixie-bws-token.cred
UNIT=dixie-stack.service
ops_dir=$(cd "$(dirname "$0")" && pwd)

# shellcheck source=lib/bws.sh
. "$ops_dir/lib/bws.sh"

[[ $EUID -eq 0 ]] || { echo "deploy.sh: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
[[ -f .env ]] || { echo "deploy.sh: $DIXIE_DIR/.env is missing; copy .env.example" >&2; exit 1; }

# Last KEY=value line in .env. Only non-secret settings live there.
setting() { sed -n "s/^$1=//p" .env | tail -n 1; }

project_id=$(setting BWS_PROJECT_ID)
remote=$(setting DEPLOY_REMOTE)
branch=$(setting DEPLOY_BRANCH)
: "${project_id:?set BWS_PROJECT_ID in .env}" "${remote:?set DEPLOY_REMOTE in .env}" "${branch:=main}"
server_url=$(setting BWS_SERVER_URL)
[[ -z $server_url ]] || export BWS_SERVER_URL="$server_url"

token=$(systemd-creds decrypt --name=bws-token "$CRED" -)
json=$(bws_project_secrets "$token" "$project_id")
unset token
key=$(bws_value "$json" DEPLOY_SSH_KEY)
unset json

eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null' EXIT
printf '%s\n' "$key" | ssh-add -q -t 300 -
unset key

# The agent holds the only key. GitHub's host keys are pinned in the repo.
export GIT_SSH_COMMAND="ssh -F none -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$ops_dir/github_known_hosts"
[[ -d .git ]] || git init --quiet --initial-branch="$branch"
git pull --ff-only "$remote" "$branch"

ssh-agent -k >/dev/null
trap - EXIT

if ! cmp -s "ops/$UNIT" "/etc/systemd/system/$UNIT"; then
	install -m 0644 "ops/$UNIT" "/etc/systemd/system/$UNIT"
	systemctl daemon-reload
fi
systemctl enable --quiet "$UNIT"

docker compose build --pull
systemctl restart "$UNIT"
systemctl --no-pager --lines=0 status "$UNIT"
