#!/usr/bin/env python3
"""Check the documentation for structure, links and leaked secrets.

Run from the repository root:  python3 tools/check_docs.py
Exits 1 and lists every problem found. Requires PyYAML.
"""
import datetime
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"

DOC_REQUIRED = ["title", "summary", "audience", "visibility", "status", "updated"]
DOC_STATUS = {"current", "planned", "draft", "historical", "superseded"}
DECISION_REQUIRED = ["id", "title", "summary", "date", "area", "status", "audience", "visibility", "updated"]
DECISION_STATUS = {"accepted", "proposed", "superseded"}
AUDIENCES = {"owner", "staff", "developer"}
VISIBILITY = {"internal", "restricted"}
META_REQUIRED = ["title", "summary", "updated", "status"]

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bsk_(live|test)_[0-9A-Za-z]{10,}"), "Stripe secret key"),
    (re.compile(r"\bwhsec_[0-9A-Za-z]{10,}"), "Stripe webhook secret"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "Google API key"),
    (re.compile(r"\bghp_[0-9A-Za-z]{30,}"), "GitHub token"),
    (re.compile(r"\b0\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[A-Za-z0-9+/=:]{20,}"), "Bitwarden access token"),
    (re.compile(r"\beyJhIjoi[0-9A-Za-z_\-]{20,}"), "Cloudflare tunnel token"),
    (re.compile(r"https://hc-ping\.com/[0-9a-f\-]{20,}"), "Healthchecks ping URL"),
    (re.compile(r"RCLONE_ENCRYPT_V0:\s*\n\s*[A-Za-z0-9+/=]{40,}"), "rclone config contents"),
]

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

problems = []


def problem(path, message):
    problems.append(f"{path.relative_to(ROOT)}: {message}")


def front_matter(path, text):
    if not text.startswith("---\n"):
        problem(path, "missing header block (must start with ---)")
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        problem(path, "header block is not closed with ---")
        return None
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        problem(path, f"header block is not valid YAML: {exc}")
        return None
    if not isinstance(data, dict):
        problem(path, "header block must be a mapping")
        return None
    return data


def check_date(path, value, field):
    if isinstance(value, datetime.date):
        return
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        problem(path, f"{field} must be a date like 2026-10-13")


def check_common(path, fm):
    audience = fm.get("audience")
    if not isinstance(audience, list) or not audience or not set(audience) <= AUDIENCES:
        problem(path, f"audience must be a list drawn from {sorted(AUDIENCES)}")
    if fm.get("visibility") not in VISIBILITY:
        problem(path, f"visibility must be one of {sorted(VISIBILITY)}")
    summary = fm.get("summary")
    if isinstance(summary, str) and len(summary) > 220:
        problem(path, "summary is longer than 220 characters")
    check_date(path, fm.get("updated"), "updated")
    for key in ("related", "supersedes", "superseded_by"):
        for target in fm.get(key) or []:
            if isinstance(target, str) and not (ROOT / target).exists():
                problem(path, f"{key} names a file that does not exist: {target}")


def check_doc(path, fm):
    for key in DOC_REQUIRED:
        if key not in fm:
            problem(path, f"header is missing '{key}'")
    if fm.get("status") not in DOC_STATUS:
        problem(path, f"status must be one of {sorted(DOC_STATUS)}")
    if fm.get("status") == "superseded" and not fm.get("superseded_by"):
        problem(path, "a superseded file must name superseded_by")
    check_common(path, fm)


def check_decision(path, fm, ids):
    for key in DECISION_REQUIRED:
        if key not in fm:
            problem(path, f"decision header is missing '{key}'")
    if fm.get("status") not in DECISION_STATUS:
        problem(path, f"decision status must be one of {sorted(DECISION_STATUS)}")
    number = int(path.name[:4])
    if fm.get("id") != number:
        problem(path, f"id {fm.get('id')} does not match the file number {number}")
    if number in ids:
        problem(path, f"decision number {number} is used twice")
    ids.add(number)
    check_date(path, fm.get("date"), "date")
    if fm.get("status") == "superseded" and not fm.get("superseded_by"):
        problem(path, "a superseded decision must name superseded_by")
    check_common(path, fm)


def check_links(path, text):
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    for target in LINK.findall(body):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        if not (path.parent / file_part).resolve().exists():
            problem(path, f"broken link: {target}")


def check_secrets(path, text):
    for pattern, label in SECRET_PATTERNS:
        if pattern.search(text):
            problem(path, f"looks like a {label} was committed")


def main():
    decision_ids = set()
    for path in sorted(DOCS.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        check_secrets(path, text)
        check_links(path, text)
        if "templates" in path.parts:
            continue
        fm = front_matter(path, text)
        if fm is None:
            continue
        if path.parent == DOCS / "decisions" and re.match(r"\d{4}-", path.name):
            check_decision(path, fm, decision_ids)
        else:
            check_doc(path, fm)

    index = DOCS / "decisions" / "README.md"
    if index.exists():
        listed = index.read_text(encoding="utf-8")
        for path in sorted((DOCS / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md")):
            if f"({path.name})" not in listed:
                problem(index, f"decision {path.name} is not listed in the index")

    for path in sorted(DATA.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        check_secrets(path, text)
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            problem(path, f"not valid YAML: {exc}")
            continue
        meta = data.get("meta") if isinstance(data, dict) else None
        if not isinstance(meta, dict):
            problem(path, "missing a top-level 'meta' block")
            continue
        for key in META_REQUIRED:
            if key not in meta:
                problem(path, f"meta is missing '{key}'")
        check_date(path, meta.get("updated"), "meta.updated")

    for path in [ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "llms.txt", ROOT / ".env.example"]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            check_secrets(path, text)
            if path.suffix == ".md" or path.name == "llms.txt":
                check_links(path, text)

    if problems:
        print(f"{len(problems)} documentation problem(s):")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
