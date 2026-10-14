#!/usr/bin/env bash
# Pulls the latest code with the deploy key, then rebuilds and restarts the
# stack. Run on the server as root:
#
#   sudo /srv/dixie-detail/ops/deploy.sh
#
# The deploy key comes from Bitwarden and lives only in a private ssh-agent
# for the length of the pull. Routine use: docs/operations/deploying-changes.md.
set -euo pipefail

DIXIE_DIR=${DIXIE_DIR:-/srv/dixie-detail}
ops_dir=$(cd "$(dirname "$0")" && pwd)

# shellcheck source=lib/bws.sh
. "$ops_dir/lib/bws.sh"
# shellcheck source=lib/settings.sh
. "$ops_dir/lib/settings.sh"

[[ $EUID -eq 0 ]] || { echo "deploy.sh: run as root (sudo)" >&2; exit 1; }
cd "$DIXIE_DIR"
[[ -f .env ]] || { echo "deploy.sh: $DIXIE_DIR/.env is missing; copy .env.example" >&2; exit 1; }

project_id=$(setting BWS_PROJECT_ID)
remote=$(setting DEPLOY_REMOTE)
branch=$(setting DEPLOY_BRANCH)
: "${project_id:?set BWS_PROJECT_ID in .env}" "${remote:?set DEPLOY_REMOTE in .env}" "${branch:=main}"
server_url=$(setting BWS_SERVER_URL)
[[ -z $server_url ]] || export BWS_SERVER_URL="$server_url"

token=$(bws_token)
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

# Install or update every unit kept in ops/.
changed=0
for unit in ops/*.service ops/*.timer; do
	if ! cmp -s "$unit" "/etc/systemd/system/${unit#ops/}"; then
		install -m 0644 "$unit" /etc/systemd/system/
		changed=1
	fi
done
((changed == 0)) || systemctl daemon-reload
systemctl enable --quiet dixie-stack.service
systemctl enable --quiet --now dixie-backup.timer dixie-public-health.timer

docker compose build --pull
systemctl restart dixie-stack.service
systemctl --no-pager --lines=0 status dixie-stack.service
