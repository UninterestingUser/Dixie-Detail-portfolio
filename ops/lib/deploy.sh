# shellcheck shell=bash
# The part of ops/deploy.sh after the pull (decision 0125). Source after
# lib/bws.sh, lib/settings.sh and lib/stack.sh, from the repository folder.
#
# The running stack is never taken down first. In order:
#   1. fetch the secrets from Bitwarden into a fresh in-memory folder;
#   2. build the images;
#   3. only then install the units, timers and folders, and
#   4. swap the new secret files in and recreate only the containers whose
#      image or settings changed (docker compose up, never down).
# If step 1 or 2 fails, nothing has been touched: the running stack is left
# as it was, and the deploy says so. When the stack isn't running at all,
# step 4 starts it with dixie-stack.service instead.
#
# SYSTEMD_UNIT_DIR, STACK_STAGE_PARENT and STACK_RUN_DIR are changed only by
# tools/test-deploy.sh.

SYSTEMD_UNIT_DIR=${SYSTEMD_UNIT_DIR:-/etc/systemd/system}
STACK_STAGE_PARENT=${STACK_STAGE_PARENT:-/run}

# deploy_unchanged MESSAGE: says the running stack wasn't touched. The caller
# returns 1 itself: under set -e a failing call here would end the shell
# before the staging folder is cleaned up.
deploy_unchanged() {
	echo "deploy.sh: $1. The running stack was left as it was; nothing was changed." >&2
}

deploy_apply() {
	local project_id server_url staged changed=0 unit timers timers_ok=1 timer health_url=""

	project_id=$(setting BWS_PROJECT_ID)
	: "${project_id:?set BWS_PROJECT_ID in .env}"
	server_url=$(setting BWS_SERVER_URL)
	[[ -z $server_url ]] || export BWS_SERVER_URL="$server_url"

	# 1. The secrets, into a fresh folder on tmpfs.
	bws_load "$project_id" || { deploy_unchanged "couldn't fetch the secrets from Bitwarden"; return 1; }
	staged=$(mktemp -d "$STACK_STAGE_PARENT/dixie-deploy.XXXXXX") || return
	# shellcheck disable=SC2064 # expand now: the folder to remove is this one
	trap "rm -rf -- '$staged'" RETURN
	stack_write_secrets "$staged/secrets" || { deploy_unchanged "couldn't write the secret files"; return 1; }
	# The health check's ping URL, kept in memory until step 3 writes its
	# credential, when that is missing.
	if [[ ! -f $HEALTH_CRED ]]; then
		health_url=$(bws_get HEALTHCHECKS_PUBLIC_URL) || { deploy_unchanged "couldn't read HEALTHCHECKS_PUBLIC_URL from Bitwarden"; return 1; }
	fi
	bws_forget

	# 2. The images.
	docker compose build --pull || { deploy_unchanged "the image build failed"; return 1; }

	# 3. Units, timers, folders and the health check's credential. None of
	# this touches a running container.
	if [[ -n $health_url ]]; then
		printf '%s' "$health_url" | systemd-creds encrypt --with-key=host+tpm2 --name="$HEALTH_CRED_NAME" - "$HEALTH_CRED"
		health_url=""
		echo "deploy.sh: wrote the health check's credential $HEALTH_CRED"
	fi
	for unit in ops/*.service ops/*.timer; do
		if ! cmp -s "$unit" "$SYSTEMD_UNIT_DIR/${unit#ops/}"; then
			install -m 0644 "$unit" "$SYSTEMD_UNIT_DIR/"
			changed=1
		fi
	done
	((changed == 0)) || systemctl daemon-reload
	systemctl enable --quiet dixie-stack.service
	# The tunnel's firewall (decision 0125), applied again in case its rules
	# changed; it only adds and replaces its own chains.
	systemctl enable --quiet dixie-tunnel-firewall.service
	systemctl restart dixie-tunnel-firewall.service
	# Every timer kept in ops/.
	timers=(ops/*.timer)
	timers=("${timers[@]#ops/}")
	systemctl enable --quiet --now "${timers[@]}"
	# The vehicle data download cache and the quote request photos, owned by
	# the app container's user (uid 10001, app/Dockerfile). An existing
	# folder is left as it is.
	[[ -d /srv/dixie-vehicle-data ]] || install -d -m 0700 -o 10001 -g 10001 /srv/dixie-vehicle-data
	[[ -d /srv/dixie-quote-photos ]] || install -d -m 0700 -o 10001 -g 10001 /srv/dixie-quote-photos

	# 4. Apply.
	if systemctl is-active --quiet dixie-stack.service; then
		# The new secret files replace the old in one rename each; containers
		# left running keep the files they mounted.
		rm -rf -- "$STACK_RUN_DIR/secrets.old"
		[[ ! -e $STACK_RUN_DIR/secrets ]] || mv -- "$STACK_RUN_DIR/secrets" "$STACK_RUN_DIR/secrets.old"
		mv -- "$staged/secrets" "$STACK_RUN_DIR/secrets"
		rm -rf -- "$STACK_RUN_DIR/secrets.old"
		if ! docker compose "${STACK_UP[@]}"; then
			echo "deploy.sh: the changed containers didn't all come up running and healthy; see docker compose ps and docs/operations/troubleshooting.md" >&2
			return 1
		fi
	else
		echo "deploy.sh: the stack wasn't running; starting it"
		systemctl start dixie-stack.service
	fi

	# Check that every timer is enabled and waiting for its next run.
	systemctl list-timers --all --no-pager "${timers[@]}"
	for timer in "${timers[@]}"; do
		if ! systemctl is-enabled --quiet "$timer" || ! systemctl is-active --quiet "$timer"; then
			echo "deploy.sh: $timer is not enabled and active; see docs/operations/troubleshooting.md" >&2
			timers_ok=0
		fi
	done
	((timers_ok)) && echo "deploy.sh: all ${#timers[@]} timers enabled and active"
	systemctl --no-pager --lines=0 status dixie-stack.service || true
	# A timer that failed the check above fails the deploy.
	((timers_ok))
}
