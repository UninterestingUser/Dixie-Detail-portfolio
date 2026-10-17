---
title: Publishing the public portfolio copy
summary: How the owner publishes and updates the public copy of this private repository, with every commit rewritten to hide server addresses and private details, and what to do when the publish script stops.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-17
tags: [portfolio, github, publishing, privacy]
related: [tools/publish-portfolio.sh, docs/decisions/0063-public-portfolio-copy.md, README.md, CLAUDE.md]
---

# Publishing the public portfolio copy

The working repository stays private. `tools/publish-portfolio.sh` builds a public copy from `main`, with every commit rewritten to replace server addresses and a few private details, and pushes it to a separate public repository that the owner uses as a portfolio. The owner publishes at milestones, such as the end of a phase. The reasons are in [decision 0063](../decisions/0063-public-portfolio-copy.md).

## What the public copy changes

- **Text replacements.** Server addresses, the tailnet name, links to private documents and a few private personal details are replaced in every version of every file and in every commit message. The rules live in a file on the owner's workstation, never in a repository, because the list names the things it hides.
- **Commit emails.** Every commit shows the owner's name with his GitHub no-reply address.
- **Everything else is copied as is,** including the full commit history. The private repository is never changed.

The script makes the same copy each time from the same input, so an update adds the new commits on top of the public history. Only a change to the replacement rules or the email mapping rewrites older commits, and that needs a force push (see the last section).

## The three settings files

They live in `"$HOME/Dixie Detail/github-portfolio"` on the Fedora workstation, readable only by the owner (`chmod 600`). The folder name has a space, so keep the path in double quotes in every command. Another folder can be used by setting `PORTFOLIO_CONF_DIR`.

| File | What it holds |
| --- | --- |
| `replacements.txt` | One rule per line, `old text==>new text`. A line starting with `regex:` is a regular expression. Longer phrases go before shorter ones, because the rules apply in order. No comments or blank lines. |
| `mailmap` | One line mapping the old commit email to the owner's name and GitHub no-reply address: `Kris Grassman <ID+UninterestingUser@users.noreply.github.com> <old email>` |
| `public-url` | One line: the public repository's URL, for example `https://github.com/UninterestingUser/dixie-detail-portfolio.git` |

## One-time setup

1. **Make the working repository private.** On GitHub, open the repository page and check the fork count first: a fork made while it was public stays public. Then Settings, General, Danger Zone, Change repository visibility, Private.
2. **Create the public repository** on GitHub, named as in `public-url`, set to Public, with no README, license or `.gitignore`, so it starts empty.
3. **Find the no-reply email.** GitHub Settings, Emails: turn on "Keep my email addresses private" and copy the address shown, which looks like `12345678+UninterestingUser@users.noreply.github.com`. Put it in `mailmap`. To use it for future commits too: `git config --global user.email "<that address>"`.
4. **Install git filter-repo:** `sudo dnf install git-filter-repo`.
5. **Put the three settings files in place:** `mkdir -p "$HOME/Dixie Detail/github-portfolio"`, copy the files in, then `chmod 600 "$HOME/Dixie Detail/github-portfolio"/*`.
6. **Publish for the first time,** from the repository on the workstation:

   ```bash
   cd ~/Projects/Dixie-Detail
   git switch main && git pull
   tools/publish-portfolio.sh --dry-run
   tools/publish-portfolio.sh
   ```

7. **Set up the public repository** on GitHub:
   - Settings, Advanced Security (or Code security): turn on Dependabot alerts, secret scanning and push protection. They are free for public repositories.
   - Settings, Rules, Rulesets, New branch ruleset: target `main`, turn on "Restrict deletions" and "Block force pushes", and set it to Active.
   - On the repository's main page, fill in About (a one-line description, the website, topics such as django, postgresql, docker, self-hosted), and pin the repository on your profile.

## Publishing an update

```bash
cd ~/Projects/Dixie-Detail
git switch main && git pull
tools/publish-portfolio.sh
```

The script clones `main` from GitHub, so it publishes only what is merged. It prints its checks, a review list and the new commits, then asks before pushing. The business phone number appears in the review list every time; that is expected, since it is public. Read the list and the commit titles before answering `y`.

## When the script stops

| Message | What it means | What to do |
| --- | --- | --- |
| `git filter-repo is not installed` | The tool is missing on this machine | `sudo dnf install git-filter-repo` |
| `missing …/replacements.txt` (or `mailmap`, `public-url`) | A settings file is not in `"$HOME/Dixie Detail/github-portfolio"` | Put it back from the owner's private copy |
| `text from the replacement list is still present` | A rule did not apply, usually a spelling difference | Copy the exact text from the printed line into the rule and run again |
| `commits still carry these emails` | A commit was made with an email the mailmap does not cover | Add that email to `mailmap` (it then needs `--force`, below) |
| Something private in the review list | A new detail the rules do not cover yet | Add a rule to `replacements.txt` and run again |
| `the rewritten history no longer matches the public copy` | The rules or the mailmap changed, so older commits changed too | In the public repository's ruleset, turn off "Block force pushes"; run `tools/publish-portfolio.sh --force`; turn the setting back on |
| `cannot reach …` | Wrong URL or not signed in | Check `public-url` and `gh auth status` |

## Keeping the public copy safe

- `CLAUDE.md` asks for everything in the repository to be written as if it were public after the replacements: no secrets, no customer data, no personal details about the owner's family, and server-specific values referred to by their setting name rather than written out.
- The checks catch text on the replacement list, common key and token formats, and commit emails. They cannot recognize a new private detail on their own, which is why the review list and the commit titles are shown before each push.
- If something private is published by mistake: replace any secret first (Bitwarden, then the service), add a rule, and publish with `--force`. GitHub Support can remove cached views of the old commits if needed.
