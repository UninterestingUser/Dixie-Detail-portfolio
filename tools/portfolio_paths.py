#!/usr/bin/env python3
"""Choose and check the paths of the public portfolio copy.

Used by tools/publish-portfolio.sh (decision 0111). Standard library only.

  portfolio_paths.py select REPO REV LIST KEEP
      Reads the include list from the file LIST (a copy of
      data/portfolio-include.txt as it is at REV) and every path in every
      commit reachable from REV in the git repository REPO. Writes the paths
      the public copy keeps to KEEP, as a git filter-repo --paths-from-file
      list. Prints how many files at REV are included and lists every file
      left out by rule.

  portfolio_paths.py check REPO REV LIST
      Looks at every path in every commit reachable from REV. Fails (exit 1)
      if any path is not on the include list or is on its exclude list, any
      path is under docs/operations/, or any version of any file is marked
      visibility: restricted.

The rules:
  - a path is a candidate only if the [include] section lists it, or a
    folder (written with a trailing /) that holds it;
  - a path under docs/operations/ is always left out;
  - a path the [exclude] section lists, or in a folder it lists, is left out;
  - a file whose header says visibility: restricted at REV is left out, and
    so is a file no longer at REV that was restricted in any commit. The
    header is a front matter block (the file starts with a --- line) or, for
    a data file, its top-level meta: block.

The choice covers every path in the history, not only the files at REV, so
a file that is renamed or deleted later keeps its earlier commits: the
public history stays the same from one publish to the next unless a rule
or the list changes.
"""
import re
import subprocess
import sys

ALWAYS_LEFT_OUT = "docs/operations/"
RESTRICTED = re.compile(rb"^\s*visibility:\s*['\"]?restricted['\"]?\s*(#.*)?$")


def die(message):
    print(f"portfolio_paths: {message}", file=sys.stderr)
    sys.exit(2)


def git(repo, *args):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if result.returncode != 0:
        die(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def parse_list(text, name):
    """Return (include, exclude) entries from the include list's text."""
    sections = {"include": [], "exclude": []}
    section = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        header = re.fullmatch(r"\[(\w+)\]", line)
        if header:
            section = header.group(1)
            if section not in sections:
                die(f"{name}:{number}: unknown section [{section}]; use [include] or [exclude]")
            continue
        if section is None:
            die(f"{name}:{number}: a path comes before the [include] section")
        if (line.startswith(("/", "./")) or "\\" in line or ".." in line.split("/")
                or any(c in line for c in "*?[]") or "==>" in line):
            die(f"{name}:{number}: {line!r} is not a plain repository path "
                "(no leading /, no .., no wildcards)")
        sections[section].append(line)
    if not sections["include"]:
        die(f"{name}: the [include] section is empty")
    return sections["include"], sections["exclude"]


def matches(entry, path):
    """A folder entry (trailing /) matches everything under it; a file entry matches itself."""
    return path.startswith(entry) if entry.endswith("/") else path == entry


def read_blobs(repo, ids):
    """Return {blob id: first 64 KiB of its content} for the given blob ids."""
    ids = sorted(set(ids))
    if not ids:
        return {}
    proc = subprocess.run(["git", "-C", repo, "cat-file", "--batch"],
                          input=b"".join(i.encode() + b"\n" for i in ids),
                          capture_output=True)
    if proc.returncode != 0:
        die(f"git cat-file failed: {proc.stderr.decode(errors='replace').strip()}")
    out, pos, blobs = proc.stdout, 0, {}
    while pos < len(out):
        end = out.index(b"\n", pos)
        oid, kind, size = out[pos:end].split(b" ")
        start = end + 1
        blobs[oid.decode()] = out[start:start + min(int(size), 65536)]
        pos = start + int(size) + 1
    return blobs


def is_restricted(content):
    lines = content.split(b"\n")
    if lines and lines[0].lstrip(b"\xef\xbb\xbf").rstrip(b"\r") == b"---":
        for line in lines[1:]:
            line = line.rstrip(b"\r")
            if line in (b"---", b"..."):
                return False
            if RESTRICTED.match(line) and not line.startswith((b" ", b"\t")):
                return True
        return False
    # A data file's top-level meta: block, as in data/*.yaml.
    in_meta = False
    for line in lines:
        line = line.rstrip(b"\r")
        if not line.strip() or line.lstrip().startswith(b"#"):
            continue
        if not line.startswith((b" ", b"\t")):
            if in_meta:
                return False
            in_meta = line.split(b"#")[0].strip() == b"meta:"
            continue
        if in_meta and RESTRICTED.match(line):
            return True
    return False


def tree(repo, rev):
    """Return {path: blob id} for every file at rev."""
    files = {}
    for entry in git(repo, "ls-tree", "-r", "-z", "--full-tree", rev).split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, kind, oid = meta.split(b" ")
        if kind == b"blob":
            files[path.decode()] = oid.decode()
    return files


def history(repo, rev):
    """Return {path: set of blob ids} over every commit reachable from rev."""
    seen = {}
    for commit in git(repo, "rev-list", rev).decode().split():
        for path, oid in tree(repo, commit).items():
            seen.setdefault(path, set()).add(oid)
    return seen


def read_list(list_file):
    with open(list_file, encoding="utf-8") as handle:
        return parse_list(handle.read(), "data/portfolio-include.txt")


def select(repo, rev, list_file, keep_out):
    include, exclude = read_list(list_file)
    head = tree(repo, rev)
    seen = history(repo, rev)
    blobs = read_blobs(repo, [oid for oids in seen.values() for oid in oids])

    kept, left_out, not_listed = [], [], 0
    for path in sorted(seen):
        if "\n" in path or "==>" in path:
            die(f"cannot publish a file named {path!r}")
        if not any(matches(e, path) for e in include):
            not_listed += path in head
        elif path.startswith(ALWAYS_LEFT_OUT):
            left_out.append((path, "under docs/operations/"))
        elif any(matches(e, path) for e in exclude):
            left_out.append((path, "on the exclude list"))
        elif path in head and is_restricted(blobs[head[path]]):
            left_out.append((path, "visibility: restricted"))
        elif path not in head and any(is_restricted(blobs[o]) for o in seen[path]):
            left_out.append((path, "restricted in an earlier commit, no longer in main"))
        else:
            kept.append(path)

    for entry in include:
        if not any(matches(entry, path) for path in head):
            where = "kept in older commits only" if any(matches(entry, p) for p in seen) else "in no commit"
            print(f"  Note: {entry} is on the include list but not in main ({where})")
    with open(keep_out, "w", encoding="utf-8") as out:
        out.writelines(f"literal:{p}\n" for p in kept)
    print(f"  Files included: {sum(p in head for p in kept)} in main "
          f"({len(kept)} paths across the history)")
    print(f"  Files left out by rule: {len(left_out)}")
    for path, reason in left_out:
        print(f"    {path}  ({reason})")
    print(f"  Files in main not on the include list: {not_listed}")


def check(repo, rev, list_file):
    include, exclude = read_list(list_file)
    seen = history(repo, rev)
    blobs = read_blobs(repo, [oid for oids in seen.values() for oid in oids])

    outside = sorted(p for p in seen
                     if not any(matches(e, p) for e in include) or any(matches(e, p) for e in exclude))
    operations = sorted(p for p in seen if p.startswith(ALWAYS_LEFT_OUT))
    restricted = sorted(p for p, oids in seen.items() if any(is_restricted(blobs[o]) for o in oids))
    problems = 0
    for paths, message in [
        (outside, "paths outside the include list, or on its exclude list, are in the history:"),
        (operations, "paths under docs/operations/ are in the history:"),
        (restricted, "files marked visibility: restricted are in the history "
                     "(a file restricted in an earlier commit goes on the [exclude] list):"),
    ]:
        if paths:
            problems = 1
            print(f"  FAIL: {message}")
            for path in paths[:10]:
                print(f"    {path}")
            if len(paths) > 10:
                print(f"    and {len(paths) - 10} more")
    return problems


def main(argv):
    if len(argv) == 5 and argv[0] == "select":
        select(*argv[1:])
        return 0
    if len(argv) == 4 and argv[0] == "check":
        return check(*argv[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
