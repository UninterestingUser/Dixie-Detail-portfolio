---
title: Workstation setup
summary: How the owner's Fedora workstation is set up to work on the repository with Git, the GitHub CLI and Claude Code, without storing secrets in plaintext.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-13
tags: [operations, workstation, fedora, git, claude-code]
related: [docs/decisions/0043-workstation-git-over-https.md, docs/operations/deploying-changes.md]
---

# Workstation setup

The repository is written on the owner's Fedora Workstation, in `~/Projects/Dixie-Detail`, mostly by Claude Code. It is a private GitHub repository.

## Tools

```bash
sudo dnf install -y git gh rclone
gh auth login
curl -fsSL https://claude.ai/install.sh | bash
```

- In `gh auth login`, answer GitHub.com, then **HTTPS**, then Yes to authenticating Git with your GitHub credentials, then log in with a web browser. gh keeps its sign-in encrypted in the GNOME login keyring, so there is no SSH key file or plaintext token on the workstation. Afterwards `gh auth status` should end its account line with `(keyring)`.
- `rclone` is needed only to authorise the server's Google Drive connection (`rclone authorize "drive" …`), because the server has no browser.
- Check Claude Code with `claude --version`, then start it in the project folder with `claude`.

## Working with Claude Code

1. Start Claude Code in `~/Projects/Dixie-Detail`. It reads `CLAUDE.md` first.
2. Give it one task at a time, phrased as an outcome, and ask it to open a pull request.
3. Read the pull request on GitHub, including any new settings, secrets or unit files it names, then merge it.
4. Pull the change onto the server: [deploying-changes.md](deploying-changes.md).

## Creating the repository (done 2026-10-13)

```bash
cd ~/Projects/Dixie-Detail
git init -b main
git add .
git commit -m "Docs starter"
gh repo create Dixie-Detail --private --source . --push
```

If `gh repo create` reports "Unable to add remote origin", the repository was still created on GitHub; link the folder by hand with `git remote set-url origin https://github.com/OWNER/Dixie-Detail.git` (or `git remote add origin …` if no origin exists) and `git push -u origin main`.
