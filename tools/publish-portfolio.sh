#!/usr/bin/env bash
# Publish the public portfolio copy of this repository.
#
# Clones main from the private repository into a temporary folder, rewrites
# every commit with git filter-repo (text replacements and commit emails kept
# in "$HOME/Dixie Detail/github-portfolio"), checks the result, and pushes it to the
# public repository. The private repository is never changed.
#
# Usage: tools/publish-portfolio.sh [--dry-run] [--force] [--yes]
#   --dry-run  rewrite and check, show what would be published, push nothing
#   --force    allow replacing the public history (needed after a change to
#              the replacement list or the mailmap)
#   --yes      push without asking
#
# See docs/operations/publishing-the-portfolio.md.

set -euo pipefail

conf_dir="${PORTFOLIO_CONF_DIR:-"$HOME/Dixie Detail/github-portfolio"}"
replacements="$conf_dir/replacements.txt"
mailmap="$conf_dir/mailmap"
public_url_file="$conf_dir/public-url"

force=0
yes=0
dry=0
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    --yes) yes=1 ;;
    --dry-run) dry=1 ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "publish-portfolio: unknown option $arg" >&2; exit 2 ;;
  esac
done

die() { echo "publish-portfolio: $*" >&2; exit 1; }

git filter-repo --version > /dev/null 2>&1 \
  || die "git filter-repo is not installed (Fedora: sudo dnf install git-filter-repo)"
[[ -s "$replacements" ]] || die "missing $replacements"
[[ -s "$mailmap" ]] || die "missing $mailmap"
[[ -s "$public_url_file" ]] || die "missing $public_url_file (one line: the public repository's URL)"
public_url="$(head -n 1 "$public_url_file")"

private_url="${PRIVATE_URL:-$(git -C "$(dirname "$0")" remote get-url origin)}"
[[ $private_url != "$public_url" ]] || die "the public URL is the same as the private repository's"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "Cloning main from $private_url"
git clone --quiet --single-branch --branch main --no-tags "$private_url" "$work/repo"
cd "$work/repo"

echo "Rewriting every commit"
git filter-repo --force \
  --replace-text "$replacements" \
  --replace-message "$replacements" \
  --mailmap "$mailmap" > "$work/filter-repo.log" 2>&1 \
  || { cat "$work/filter-repo.log" >&2; die "git filter-repo failed"; }

echo "Checking the rewritten copy"
problems=0
history="$work/history.txt"
content="$work/content.txt"
git log -p --format='commit %H%n%n%B' main > "$history"
git log -p --format= main > "$content"

# 1. Nothing on the replacement list survives, in files or commit messages.
grep -v -E '^(regex|glob):' "$replacements" | sed 's/==>.*$//' | sed '/^$/d' > "$work/literal.txt"
grep '^regex:' "$replacements" | sed -e 's/^regex://' -e 's/==>.*$//' > "$work/regex.txt" || true
if grep -n -F -f "$work/literal.txt" "$history" > "$work/hits.txt"; then
  echo "  FAIL: text from the replacement list is still present:"
  head -n 10 "$work/hits.txt" | cut -c 1-160 | sed 's/^/    /'
  problems=1
fi
if [[ -s $work/regex.txt ]] && grep -n -P "$(paste -s -d '|' "$work/regex.txt")" "$history" > "$work/hits.txt"; then
  echo "  FAIL: a regex from the replacement list still matches:"
  head -n 10 "$work/hits.txt" | cut -c 1-160 | sed 's/^/    /'
  problems=1
fi

# 2. No credentials in any version of any file.
secret_patterns='BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|sk_(live|test)_[A-Za-z0-9]{10,}|rk_live_[A-Za-z0-9]{10,}|whsec_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16}|xox[abposr]-[A-Za-z0-9-]{10,}|hc-ping\.com/[0-9a-f-]{20,}|eyJ[A-Za-z0-9_-]{40,}|0\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[A-Za-z0-9]{10,}'
if grep -n -E "$secret_patterns" "$content" > "$work/hits.txt"; then
  echo "  FAIL: something that looks like a key or token:"
  head -n 10 "$work/hits.txt" | cut -c 1-160 | sed 's/^/    /'
  problems=1
fi

# 3. Every author and committer email is a no-reply address.
git log --format='%ae%n%ce' main | sort -u > "$work/emails.txt"
if grep -v -E '(@users\.noreply\.github\.com|^noreply@github\.com)$' "$work/emails.txt" > "$work/hits.txt"; then
  echo "  FAIL: commits still carry these emails (add them to the mailmap):"
  sed 's/^/    /' "$work/hits.txt"
  problems=1
fi

# 4. For review: email addresses and phone numbers in file content.
grep -o -h -E '[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$content" \
  | grep -v -i -E '(^noreply@anthropic\.com|^git@github\.com|@users\.noreply\.github\.com|@example\.(com|org|net))$' \
  | sort -u > "$work/review-emails.txt" || true
grep -o -h -E '\(?\b[2-9][0-9]{2}\)?[-. ][0-9]{3}[-.][0-9]{4}\b|\b[2-9][0-9]{2}[2-9][0-9]{6}\b' "$content" \
  | tr -d '(). -' | grep -v -E '^[0-9]{3}555' | sort -u > "$work/review-phones.txt" || true
if [[ -s $work/review-emails.txt || -s $work/review-phones.txt ]]; then
  echo "  Review: these appear in the files; make sure each is public business information:"
  sed 's/^/    email /' "$work/review-emails.txt"
  sed 's/^/    phone /' "$work/review-phones.txt"
fi

[[ $problems -eq 0 ]] || die "nothing was published. Fix the items above (usually a new line in $replacements) and run again."
echo "  Checks passed."

# Compare with what is already public.
git remote add public "$public_url"
remote_heads="$(git ls-remote --heads public)" || die "cannot reach $public_url"
push_args=(public main)
if grep -q 'refs/heads/main$' <<< "$remote_heads"; then
  git fetch --quiet public main
  public_head="$(git rev-parse FETCH_HEAD)"
  if git merge-base --is-ancestor "$public_head" main; then
    count="$(git rev-list --count "$public_head"..main)"
    if [[ $count -eq 0 ]]; then
      echo "The public copy is already up to date."
      exit 0
    fi
    echo "$count new commit(s) to publish:"
    git log --oneline "$public_head"..main | sed 's/^/  /'
  else
    [[ $force -eq 1 ]] || die "the rewritten history no longer matches the public copy, usually because the replacement list or the mailmap changed. Allow force pushes in the public repository's ruleset, then run again with --force."
    echo "The public history will be replaced (--force)."
    push_args=(--force-with-lease="main:$public_head" public main)
  fi
else
  echo "First publish: $(git rev-list --count main) commits."
fi

if [[ $dry -eq 1 ]]; then
  echo "Dry run: nothing was pushed."
  exit 0
fi
if [[ $yes -ne 1 ]]; then
  read -r -p "Push to $public_url? [y/N] " answer
  [[ $answer == [yY] ]] || die "nothing was pushed."
fi
git push --quiet "${push_args[@]}"
echo "Published to $public_url"
