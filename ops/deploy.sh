#!/usr/bin/env bash
# Pulls the latest code with the deploy key, fetches the secrets and builds
# the images, and only then recreates the containers that changed: the
# running stack is never taken down first, and a failed fetch or build
# leaves it as it was (decision 0125). Run on the server as root:
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

# Everything after the pull: fetch and build first, then install, then
# recreate only what changed, never taking the running stack down first
# (ops/lib/deploy.sh, decision 0125).
# shellcheck source=lib/stack.sh
. "$ops_dir/lib/stack.sh"
# shellcheck source=lib/deploy.sh
. "$ops_dir/lib/deploy.sh"
deploy_apply
