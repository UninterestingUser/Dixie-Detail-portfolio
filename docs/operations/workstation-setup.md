---
title: Workstation setup
summary: How the owner's Fedora workstation is set up to work on the repository with Git, the GitHub CLI, Podman and Claude Code, and how to run the tests, without storing secrets in plaintext.
audience: [owner, developer]
visibility: internal
status: current
updated: 2026-10-14
tags: [operations, workstation, fedora, git, claude-code, tests, podman]
related: [docs/decisions/0043-workstation-git-over-https.md, docs/decisions/0045-development-made-up-values.md, docs/operations/deploying-changes.md]
---

# Workstation setup

The repository is written on the owner's Fedora Workstation, in `~/Projects/Dixie-Detail`, mostly by Claude Code. It is a private GitHub repository.

## Tools

```bash
sudo dnf install -y git gh rclone podman python3-pyyaml
gh auth login
curl -fsSL https://claude.ai/install.sh | bash
```

- In `gh auth login`, answer GitHub.com, then **HTTPS**, then Yes to authenticating Git with your GitHub credentials, then log in with a web browser. gh keeps its sign-in encrypted in the GNOME login keyring, so there is no SSH key file or plaintext token on the workstation. Afterwards `gh auth status` should end its account line with `(keyring)`.
- `podman` runs the tests' containers and `python3-pyyaml` lets `tools/check_docs.py` read YAML. Fedora Workstation usually has both already; the command above changes nothing if so. Docker is not needed.
- `rclone` is needed only to authorise the server's Google Drive connection (`rclone authorize "drive" …`), because the server has no browser.
- Check Claude Code with `claude --version`, then start it in the project folder with `claude`.

## Running the tests

```bash
cd ~/Projects/Dixie-Detail
tools/run-tests.sh
```

The test command does the same thing on the workstation and on GitHub Actions, which runs it on every pull request:

1. Builds a test image from the same Python base and requirements as the production app, plus pytest.
2. Starts a throwaway PostgreSQL 18 database, the same image as the server's, held in memory with no port open on the workstation.
3. Runs pytest with the development settings, `app/dixie/settings_dev.py`. Every value in that file is made up; no Bitwarden sign-in is needed (decision 0045).
4. Builds the production image and fails if it contains the development settings.
5. Removes the database, pass or fail. The run ends with `run-tests: PASS`.

Arguments go to pytest, for example `tools/run-tests.sh -k health -v`. The first run downloads the Python and PostgreSQL images, which takes a few minutes; later runs take seconds. Python does not need to be installed for the tests, because they run inside the container.

## Working with Claude Code

1. Start Claude Code in `~/Projects/Dixie-Detail`. It reads `CLAUDE.md` first.
2. Give it one task at a time, phrased as an outcome, and ask it to open a pull request.
3. Check that the pull request's Tests and Docs checks are green. Read the pull request on GitHub, including any new settings, secrets or unit files it names, then merge it.
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
