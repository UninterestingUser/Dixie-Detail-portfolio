#!/usr/bin/env bash
# pass always succeeds, so "test && pass || fail" is safe in this file.
# shellcheck disable=SC2015
# Tests tools/publish-portfolio.sh and tools/portfolio_paths.py (decision
# 0111) against throwaway repositories: a made-up "private" repository with
# an include list, restricted and operations docs, an excluded folder, a
# renamed file and a file not on the list, published to a local bare
# "public" repository with made-up replacement rules and mailmap.
# Checks that every commit of the public copy holds only paths on the list,
# that the left-out files are in no commit, that the text replacements and
# the mailmap still apply, that a second publish adds commits on top, and
# that each new check stops a publish it should stop.
# Needs bash, git, git filter-repo and python3; no network and no real
# settings. Run by tools/run-tests.sh, or on its own:  tools/test-portfolio.sh
set -euo pipefail
export LC_ALL=C

repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
failures=0

pass() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; failures=$((failures + 1)); }

git filter-repo --version >/dev/null 2>&1 || {
	echo "test-portfolio: git filter-repo is not installed (Fedora: sudo dnf install git-filter-repo)" >&2
	exit 1
}

# Made-up identities and settings; nothing here is real.
export GIT_AUTHOR_NAME="Test Owner" GIT_AUTHOR_EMAIL="owner@private.test"
export GIT_COMMITTER_NAME="Test Owner" GIT_COMMITTER_EMAIL="owner@private.test"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export PORTFOLIO_CONF_DIR="$work/conf"
mkdir -p "$PORTFOLIO_CONF_DIR"
echo 'made-up-server.tailnet.test==>SERVER' >"$PORTFOLIO_CONF_DIR/replacements.txt"
echo 'Test Owner <1+owner@users.noreply.github.com> <owner@private.test>' >"$PORTFOLIO_CONF_DIR/mailmap"
git init -q --bare -b main "$work/public.git"
echo "$work/public.git" >"$PORTFOLIO_CONF_DIR/public-url"
git init -q --bare -b main "$work/private.git"
export PRIVATE_URL="$work/private.git"

git init -q -b main "$work/src"
cd "$work/src"
commit() { git add -A && git commit -q -m "$1" && git push -q "$PRIVATE_URL" main; }
doc() { # doc PATH VISIBILITY [TEXT]
	mkdir -p "$(dirname "$1")"
	printf -- '---\ntitle: A made-up doc\nvisibility: %s\nstatus: current\n---\n\n%s\n' "$2" "${3:-Text.}" >"$1"
}

# Commit 1: the list, files on it and off it, and every kind left out by rule.
mkdir -p data app site/public/images/vehicle-classes private-notes
cat >data/portfolio-include.txt <<'LIST'
# Made-up include list for the test.
[include]
app/
site/
data/
docs/reference/
docs/operations/
README.md

[exclude]
site/public/images/vehicle-classes/
LIST
echo 'print("hello")' >app/main.py
echo 'Runs on made-up-server.tailnet.test.' >README.md
echo picture >site/public/images/vehicle-classes/small.webp
echo 'site' >site/index.html
echo 'not for the public' >private-notes/notes.txt
printf 'meta:\n  title: Made-up data\n  visibility: restricted\nvalue: 1\n' >data/restricted.yaml
printf 'meta:\n  title: Made-up data\nvalue: 2\n' >data/open.yaml
doc docs/reference/open.md internal
doc docs/reference/secret-plan.md restricted
doc docs/reference/old-name.md internal
doc docs/reference/gone-restricted.md restricted
doc docs/operations/runbook.md internal
commit "First commit"
# Commit 2: a rename and a deleted restricted file, which must not rewrite
# earlier public commits on the next publish or leak the deleted file.
git mv docs/reference/old-name.md docs/reference/new-name.md
git rm -q docs/reference/gone-restricted.md
commit "Rename a doc and delete a restricted one"
# Commit 3: touches only left-out files, so the public copy drops it.
echo more >>private-notes/notes.txt
doc docs/operations/runbook.md internal "Changed."
commit "Only left-out files"
cd "$repo"

publish() { "$repo/tools/publish-portfolio.sh" "$@" >"$work/out.txt" 2>&1; }

echo "test-portfolio: the first publish"
publish --yes && pass "the first publish succeeds" || { fail "the first publish failed"; cat "$work/out.txt" >&2; }
git clone -q "$work/public.git" "$work/pub"
all_paths=$(git -C "$work/pub" log --format= --name-only --all | sort -u | sed '/^$/d')
expected=$(printf '%s\n' README.md app/main.py data/open.yaml data/portfolio-include.txt \
	docs/reference/new-name.md docs/reference/old-name.md docs/reference/open.md site/index.html)
[[ $all_paths == "$expected" ]] && pass "every commit holds only the paths on the include list" ||
	fail "the public history holds: $(echo "$all_paths" | tr '\n' ' ')"
for gone in docs/operations/runbook.md docs/reference/secret-plan.md docs/reference/gone-restricted.md \
	data/restricted.yaml site/public/images/vehicle-classes/small.webp private-notes/notes.txt; do
	grep -qxF "$gone" <<<"$all_paths" && fail "$gone is in the public history" || pass "$gone is in no public commit"
done
grep -q 'made-up-server' "$work/pub/README.md" && fail "the text replacement did not run" ||
	pass "the text replacements still run after the path filter"
[[ $(git -C "$work/pub" log --format='%ae' | sort -u) == 1+owner@users.noreply.github.com ]] &&
	pass "the mailmap still runs" || fail "commit emails were not mapped"
[[ $(git -C "$work/pub" rev-list --count main) == 2 ]] && pass "a commit that changed only left-out files is dropped" ||
	fail "expected 2 public commits, got $(git -C "$work/pub" rev-list --count main)"
grep -q 'Files left out by rule: 5' "$work/out.txt" && grep -q 'secret-plan.md  (visibility: restricted)' "$work/out.txt" &&
	grep -q 'gone-restricted.md  (restricted in an earlier commit' "$work/out.txt" &&
	grep -q 'runbook.md  (under docs/operations/)' "$work/out.txt" &&
	grep -q 'small.webp  (on the exclude list)' "$work/out.txt" &&
	grep -q 'Files in main not on the include list: 1' "$work/out.txt" &&
	grep -q '2 of 3 commits kept' "$work/out.txt" &&
	pass "the summary counts the files and commits" || { fail "the summary is wrong"; cat "$work/out.txt" >&2; }

echo "test-portfolio: an update adds commits on top"
first_head=$(git -C "$work/public.git" rev-parse main)
cd "$work/src"
echo 'print("two")' >app/two.py
git rm -q docs/reference/new-name.md
commit "Add a file and delete a published one"
cd "$repo"
publish --yes && pass "the update publishes without --force" || { fail "the update needed --force"; cat "$work/out.txt" >&2; }
git -C "$work/public.git" merge-base --is-ancestor "$first_head" main &&
	pass "the earlier public commits are unchanged" || fail "the update rewrote earlier public commits"

echo "test-portfolio: the include list's checks stop a publish"
cd "$work/src"
# A file that was restricted and is now internal: its older versions would
# be published, so the check stops it until it goes on the exclude list.
doc docs/reference/secret-plan.md internal
commit "Lower a doc's visibility"
cd "$repo"
publish --dry-run && fail "a file restricted in an earlier commit was published" ||
	{ grep -q 'visibility: restricted are in the history' "$work/out.txt" && grep -q 'secret-plan.md' "$work/out.txt" &&
		pass "a file restricted in an earlier commit stops the publish" || { fail "wrong message"; cat "$work/out.txt" >&2; }; }
cd "$work/src"
printf '[exclude]\ndocs/reference/secret-plan.md\n' >>data/portfolio-include.txt
commit "Exclude the lowered doc"
cd "$repo"
publish --dry-run && pass "an exclude entry lets the publish go ahead" || { fail "the exclude entry did not help"; cat "$work/out.txt" >&2; }

cd "$work/src"
sed -i 's#^docs/reference/$#docs/reference/../#' data/portfolio-include.txt
commit "A bad include entry"
cd "$repo"
publish --dry-run && fail "a path with .. was accepted" ||
	{ grep -q 'is not a plain repository path' "$work/out.txt" && pass "a path with .. is refused" ||
		{ fail "wrong message"; cat "$work/out.txt" >&2; }; }

echo "test-portfolio: the history check on its own"
# The check must catch what a broken path filter would leave behind.
git init -q -b main "$work/bad"
cd "$work/bad"
printf '[include]\ndocs/\nnotes.txt\n[exclude]\ndocs/private/\n' >"$work/list.txt"
doc docs/operations/a.md internal
doc docs/reference/b.md restricted
doc docs/private/c.md internal
echo x >outside.txt
echo y >notes.txt
git add -A && git commit -q -m one
cd "$repo"
python3 "$repo/tools/portfolio_paths.py" check "$work/bad" main "$work/list.txt" >"$work/out.txt" 2>&1 &&
	fail "the check passed a bad history" || {
	grep -q 'outside.txt' "$work/out.txt" && grep -q 'docs/private/c.md' "$work/out.txt" &&
		pass "the check finds paths outside the list and on the exclude list" || fail "the check missed an outside path"
	grep -A2 'docs/operations/ are in the history' "$work/out.txt" | grep -q 'docs/operations/a.md' &&
		pass "the check finds docs/operations/" || fail "the check missed docs/operations/"
	grep -A1 'restricted are in the history' "$work/out.txt" | grep -q 'docs/reference/b.md' &&
		pass "the check finds a restricted file" || fail "the check missed a restricted file"
}

if ((failures)); then
	echo "test-portfolio: $failures failure(s)" >&2
	exit 1
fi
echo "test-portfolio: PASS"
