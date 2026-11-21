#!/usr/bin/env bash
# Deploys the offline replay Worker without editing any file (decision 0116).
#
# wrangler.toml keeps a placeholder for the KV namespace id. This script asks
# the Cloudflare account for the namespace titled OFFLINE_REQUESTS, writes a
# copy of wrangler.toml with the real id beside it (git ignores it), deploys
# with that copy and removes it, so no account value is ever left as a local
# change or committed. Run it from anywhere on the workstation, after
# `npx wrangler@4.48.0 login`:
#
#   site/workers/offline-replay/deploy.sh          # deploy the Worker
#   site/workers/offline-replay/deploy.sh --id     # print the namespace id only,
#                                                  # for the `kv key` commands
#
# Any other arguments are passed on to `wrangler deploy`, such as
# --dry-run. WRANGLER overrides the command, for tools/test-worker-deploy.sh.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
read -r -a wrangler <<<"${WRANGLER:-npx --yes wrangler@4.48.0}"
title=OFFLINE_REQUESTS
placeholder=SET_TO_THE_OFFLINE_REQUESTS_NAMESPACE_ID
config="$here/wrangler.toml"

grep -q "id = \"$placeholder\"" "$config" || {
	echo "deploy: wrangler.toml no longer holds the placeholder id $placeholder; put it back, the id is looked up at deploy time" >&2
	exit 1
}

# The namespace list is JSON on stdout: [{"id": ..., "title": ...}, ...].
list=$(cd "$here" && "${wrangler[@]}" kv namespace list --config "$config") || {
	echo "deploy: couldn't list the account's KV namespaces; run npx wrangler@4.48.0 login first" >&2
	exit 1
}
id=$(TITLE=$title node -e '
	let list;
	try { list = JSON.parse(require("fs").readFileSync(0, "utf8")); } catch { process.exit(3); }
	const found = list.filter((n) => n.title === process.env.TITLE);
	if (found.length !== 1) process.exit(found.length ? 4 : 2);
	if (!/^[0-9a-f]{32}$/.test(found[0].id)) process.exit(3);
	console.log(found[0].id);
' <<<"$list") || {
	case $? in
		2) echo "deploy: no KV namespace titled $title in this Cloudflare account; create it with npx wrangler@4.48.0 kv namespace create $title" >&2 ;;
		4) echo "deploy: more than one KV namespace is titled $title; rename or delete the extra one in the dashboard" >&2 ;;
		*) echo "deploy: couldn't read wrangler's list of KV namespaces" >&2 ;;
	esac
	exit 1
}

if [[ ${1:-} == --id ]]; then
	echo "$id"
	exit 0
fi

# Beside wrangler.toml, so main = "index.js" resolves the same way.
deploy_config=$(mktemp "$here/.wrangler-deploy-XXXXXX.toml")
trap 'rm -f -- "$deploy_config"' EXIT
sed "s/id = \"$placeholder\"/id = \"$id\"/" "$config" >"$deploy_config"
echo "deploy: KV namespace $title is $id"
(cd "$here" && "${wrangler[@]}" deploy --config "$deploy_config" "$@")
