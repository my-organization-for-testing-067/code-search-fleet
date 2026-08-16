#!/usr/bin/env python3
"""Answer "who owns this" from CODEOWNERS files across the fleet.

The question this fills in: every other cs subcommand tells you WHERE something
is, and the next thing anyone asks is who to talk to about it. In a single repo
that is a `cat CODEOWNERS` away. Across a fleet it is not -- the file you found
with `cs uses` is in a repo you have never opened, whose ownership rules live in
one of four conventional locations and whose last matching rule wins.

This is a `declared` answer, in the same sense as deps.py: it reports what the
file says, which is not necessarily who will actually review your PR. See the
blind spots in `cs why declared` and the caveats printed by `cs owns`.

Usage:
  owners.py <fleet-root> file   <repo>/<path>   who owns one path
  owners.py <fleet-root> repo   <repo>          every rule in one repo
  owners.py <fleet-root> audit                  which repos declare ownership
"""
import pathlib
import re
import sys

# The four locations git and the major forges look in, in the order they take
# precedence. GitHub reads root, docs/, then .github/; GitLab adds .gitlab/.
# Checking all of them and reporting which one was used matters because a repo
# with two of these has one that is silently ignored.
CODEOWNERS_PATHS = [
    "CODEOWNERS",
    ".github/CODEOWNERS",
    "docs/CODEOWNERS",
    ".gitlab/CODEOWNERS",
]


def find_codeowners(repo):
    """Every CODEOWNERS in this repo, as (relative-path, text) pairs."""
    found = []
    for rel in CODEOWNERS_PATHS:
        p = repo / rel
        if p.is_file():
            try:
                found.append((rel, p.read_text(errors="replace")))
            except OSError:
                pass
    return found


def parse(text):
    """[(pattern, [owners], line_number)] in file order."""
    rules = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            # A pattern with no owners is legal and means "unset ownership".
            rules.append((parts[0], [], n))
            continue
        rules.append((parts[0], parts[1:], n))
    return rules


def pattern_to_regex(pattern):
    """gitignore-style CODEOWNERS pattern -> compiled regex over a repo path.

    Only the subset CODEOWNERS actually uses is implemented: `*` which does not
    cross a separator, `**` which does, a leading `/` to anchor at the repo
    root, and a trailing `/` for directories. Character classes and `?` are
    deliberately not supported -- guessing at them would produce confident wrong
    owners, and an unsupported pattern is reported instead.
    """
    anchored = pattern.startswith("/")
    dir_only = pattern.endswith("/")
    p = pattern.strip("/") if anchored else pattern.rstrip("/")

    out = []
    i = 0
    while i < len(p):
        c = p[i]
        if c == "*":
            if p[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c in ".^$+{}[]()|\\":
            out.append("\\" + c)
        else:
            out.append(c)
        i += 1
    body = "".join(out)

    # An unanchored pattern with no separator matches at any depth, which is the
    # rule most often got wrong by hand: `*.py` owns every .py in the repo, not
    # only those at the root.
    if not anchored and "/" not in p:
        prefix = r"(?:.*/)?"
    else:
        prefix = ""

    suffix = "/.*" if dir_only else "(?:/.*)?"
    return re.compile("^" + prefix + body + suffix + "$")


def owners_for(rules, path):
    """(owners, pattern, line) for a repo-relative path. Last match wins."""
    match = None
    for pattern, owners, line in rules:
        try:
            rx = pattern_to_regex(pattern)
        except re.error:
            continue
        if rx.match(path):
            match = (owners, pattern, line)
    return match


def repos(root):
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def cmd_file(root, spec):
    if "/" not in spec:
        print(f"expected <repo>/<path>, got '{spec}'", file=sys.stderr)
        return 2
    repo_name, rel = spec.split("/", 1)
    repo = root / repo_name
    if not repo.is_dir():
        print(f"no such repo in the fleet: {repo_name}", file=sys.stderr)
        return 2

    files = find_codeowners(repo)
    if not files:
        print(f"{repo_name}\t(no CODEOWNERS)\t-", file=sys.stderr)
        return 1

    src, text = files[0]
    match = owners_for(parse(text), rel)
    if match is None:
        print(f"{repo_name}/{rel}\t(no rule matches)\t{src}", file=sys.stderr)
        return 1
    owners, pattern, line = match
    if not owners:
        print(f"{repo_name}/{rel}\t(ownership explicitly unset)\t{src}:{line} [{pattern}]",
              file=sys.stderr)
        return 1
    print("{}/{}\t{}\t{}:{} [{}]".format(
        repo_name, rel, " ".join(owners), src, line, pattern))
    if len(files) > 1:
        print("  note: {} also has {}, which is ignored".format(
            repo_name, ", ".join(s for s, _ in files[1:])), file=sys.stderr)
    return 0


def cmd_repo(root, repo_name):
    repo = root / repo_name
    if not repo.is_dir():
        print(f"no such repo in the fleet: {repo_name}", file=sys.stderr)
        return 2
    files = find_codeowners(repo)
    if not files:
        print(f"{repo_name} declares no CODEOWNERS", file=sys.stderr)
        return 1
    for src, text in files:
        for pattern, owners, line in parse(text):
            print("{}/{}:{}: {}\t{}".format(
                repo_name, src, line, pattern, " ".join(owners) or "(unset)"))
    return 0


def cmd_audit(root):
    """Which repos declare ownership at all -- the gap is the useful part."""
    rows, missing = [], []
    for repo in repos(root):
        files = find_codeowners(repo)
        if not files:
            missing.append(repo.name)
            continue
        n = sum(len(parse(t)) for _, t in files)
        rows.append((repo.name, ", ".join(s for s, _ in files), n))
    for name, srcs, n in rows:
        print(f"{name}\t{n} rule(s)\t{srcs}")
    for name in missing:
        print(f"{name}\t-\tno CODEOWNERS", file=sys.stderr)
    return 0 if rows else 1


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    root = pathlib.Path(sys.argv[1])
    if not root.is_dir():
        print(f"no such fleet root: {root}", file=sys.stderr)
        return 2
    cmd = sys.argv[2]
    arg = sys.argv[3] if len(sys.argv) > 3 else None

    if cmd == "audit":
        return cmd_audit(root)
    if arg is None:
        print(f"usage: owners.py <root> {cmd} <arg>", file=sys.stderr)
        return 2
    if cmd == "file":
        return cmd_file(root, arg)
    if cmd == "repo":
        return cmd_repo(root, arg)
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
