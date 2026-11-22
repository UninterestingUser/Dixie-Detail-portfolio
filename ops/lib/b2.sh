# shellcheck shell=bash
# Checks that the Backblaze B2 bucket holds nothing but restic's encrypted
# repository (decision 0127). Source after lib/restic.sh; needs b2_key_id
# and b2_application_key (restic_load_secrets ... b2) and B2_REPOSITORY.
#
# The bucket is listed with curl's own AWS signature support, through B2's
# S3-compatible API. The key goes to curl in a config on its stdin, never on
# a command line, as hc_ping does with its URL.
# shellcheck disable=SC2154 # b2_key_id and b2_application_key: set by the caller

# The names restic gives the files of a repository, under its folder.
B2_REPOSITORY_FILE='^(config|keys/[0-9a-f]{64}|data/[0-9a-f]{2}/[0-9a-f]{64}|index/[0-9a-f]{64}|snapshots/[0-9a-f]{64}|locks/[0-9a-f]{64})$'

# b2_parse_repository: sets b2_endpoint (https://host), b2_region, b2_bucket
# and b2_prefix (the repository's folder in the bucket, maybe empty) from
# B2_REPOSITORY, which looks like
#   s3:https://s3.us-west-004.backblazeb2.com/BUCKET/FOLDER
b2_parse_repository() {
	local rest=${B2_REPOSITORY#s3:}
	[[ $rest =~ ^(https://([^/]+))/([^/]+)/?(.*)$ ]] ||
		{ echo "b2: B2_REPOSITORY isn't s3:https://HOST/BUCKET[/FOLDER]" >&2; return 1; }
	b2_endpoint=${BASH_REMATCH[1]}
	b2_bucket=${BASH_REMATCH[3]}
	b2_prefix=${BASH_REMATCH[4]%/}
	[[ ${BASH_REMATCH[2]} =~ ^s3\.([a-z0-9-]+)\.backblazeb2\.com$ ]] ||
		{ echo "b2: B2_REPOSITORY's host isn't s3.REGION.backblazeb2.com" >&2; return 1; }
	b2_region=${BASH_REMATCH[1]}
}

# b2_list_files: prints the name of every file in the whole bucket, one a
# line, following the listing's continuation tokens.
b2_list_files() {
	local token="" page query
	b2_parse_repository || return
	while :; do
		query="list-type=2&max-keys=1000"
		[[ -z $token ]] || query+="&continuation-token=$(jq -rn --arg t "$token" '$t | @uri')"
		page=$(printf 'url = "%s/%s?%s"\nuser = "%s:%s"\naws-sigv4 = "aws:amz:%s:s3"\n' \
			"$b2_endpoint" "$b2_bucket" "$query" "$b2_key_id" "$b2_application_key" "$b2_region" |
			curl --fail --silent --show-error --max-time 60 --retry 3 --config -) ||
			{ echo "b2: couldn't list the bucket $b2_bucket" >&2; return 1; }
		grep -o '<Key>[^<]*</Key>' <<<"$page" | sed 's/<Key>\(.*\)<\/Key>/\1/' || true
		[[ $page == *"<IsTruncated>true</IsTruncated>"* ]] || return 0
		token=$(sed -n 's/.*<NextContinuationToken>\([^<]*\)<\/NextContinuationToken>.*/\1/p' <<<"$page")
		[[ -n $token ]] || { echo "b2: the listing was cut short without a continuation token" >&2; return 1; }
	done
}

# b2_check_only_repository_files: lists the bucket and fails, naming each
# one, if any file is outside the repository's folder or isn't named as
# restic names its files.
b2_check_only_repository_files() {
	local files name inside bad=0 count=0
	# Here, not only inside b2_list_files, whose $(...) keeps its settings.
	b2_parse_repository || return
	files=$(b2_list_files) || return
	while IFS= read -r name; do
		[[ -n $name ]] || continue
		count=$((count + 1))
		inside=$name
		if [[ -n $b2_prefix ]]; then
			if [[ $name != "$b2_prefix/"* ]]; then
				echo "b2: FAIL: $name is outside the repository's folder $b2_prefix/" >&2
				bad=$((bad + 1))
				continue
			fi
			inside=${name#"$b2_prefix/"}
		fi
		if [[ ! $inside =~ $B2_REPOSITORY_FILE ]]; then
			echo "b2: FAIL: $name isn't a restic repository file" >&2
			bad=$((bad + 1))
		fi
	done <<<"$files"
	if ((bad)); then
		echo "b2: $bad of $count file(s) in the bucket $b2_bucket aren't restic's repository; nothing may reach B2 outside restic" >&2
		return 1
	fi
	echo "b2: all $count file(s) in the bucket $b2_bucket are restic's encrypted repository"
}
