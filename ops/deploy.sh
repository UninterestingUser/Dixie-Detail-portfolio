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

# Bash reads a script from the file it opened as it goes, so after the pull
# the rest of this run would still be the old deploy.sh: a new timer would be
# installed but not enabled. The pull therefore ends by starting the pulled
# deploy.sh, which skips straight to the steps after it.
if [[ -z ${DIXIE_DEPLOY_PULLED:-} ]]; then
	project_id=$(setting BWS_PROJECT_ID)
	remote=$(setting DEPLOY_REMOTE)
	branch=$(setting DEPLOY_BRANCH)
	: "${project_id:?set BWS_PROJECT_ID in .env}" "${remote:?set DEPLOY_REMOTE in .env}" "${branch:=main}"
	server_url=$(setting BWS_SERVER_URL)
	[[ -z $server_url ]] || export BWS_SERVER_URL="$server_url"

	bws_load "$project_id"
	key=$(bws_get DEPLOY_SSH_KEY)
	bws_forget

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
	exec env DIXIE_DEPLOY_PULLED=1 "$DIXIE_DIR/ops/deploy.sh"
fi

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
# Every timer kept in ops/: the backup, the public health check and the
# vehicle data refresh.
timers=(ops/*.timer)
timers=("${timers[@]#ops/}")
systemctl enable --quiet --now "${timers[@]}"

# The vehicle data download cache, outside the repository, owned by the app
# container's user (uid 10001, app/Dockerfile), so a rebuilt server needs no
# manual step. An existing folder is left as it is.
[[ -d /srv/dixie-vehicle-data ]] || install -d -m 0700 -o 10001 -g 10001 /srv/dixie-vehicle-data

docker compose build --pull
systemctl restart dixie-stack.service

# Check that every timer is enabled and waiting for its next run.
systemctl list-timers --all --no-pager "${timers[@]}"
timers_ok=1
for timer in "${timers[@]}"; do
	if ! systemctl is-enabled --quiet "$timer" || ! systemctl is-active --quiet "$timer"; then
		echo "deploy.sh: $timer is not enabled and active; see docs/operations/troubleshooting.md" >&2
		timers_ok=0
	fi
done
((timers_ok)) && echo "deploy.sh: all ${#timers[@]} timers enabled and active"

systemctl --no-pager --lines=0 status dixie-stack.service

# A timer that failed the check above fails the deploy.
((timers_ok))
