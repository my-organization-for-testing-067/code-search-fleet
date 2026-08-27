#!/usr/bin/env python3
"""Ask the forge's ORG-WIDE code search what the fleet cannot see.

The gap this closes: cs is careful about whether the SEARCH was sound -- zero
hits are distinguished from a refusal, a timeout rules nothing out, PARTIAL is
disclosed, --source-only names what it dropped. None of that says anything about
whether the CORPUS was sound. A fleet holding 43 of an org's 365 repos makes
`cs uses <route>` returning nothing mean "not in these 43", and a caller reading
it as "nothing at this company calls it" is wrong in a way no provenance on the
search itself can catch. The proof is set-theoretic, not search-dependent: no
query shape can find a repo that was never cloned.

cs is the right place for it because cs is the only component that knows what
the fleet contains -- it already prints the denominator, it just could not
compare it to anything.

Three things measured the hard way, each of which is a rule here:

  1. A SUPPRESSED STDERR TURNS A 403 INTO A FALSE ZERO. Org-wide code search is
     rate limited, and a sweep that hid the error reported a repo as having no
     hits for anything -- including a term that was definitely present -- because
     it had silently stopped being searched. So a non-zero exit, or output that
     does not parse, is a REFUSAL here and never an empty result. Nothing in
     this file counts lines from a call whose status it did not check.
  2. EXTENSION FILTERS HIDE THE BEST EVIDENCE. A sweep filtered to *.py returned
     nothing for the repo that most deserved cloning, because the relevant
     declarations lived in .yaml and .md data-model files. Search unfiltered,
     classify afterwards.
  3. APPLICATION CODE AND CONFIG-ONLY ARE DIFFERENT FINDINGS. Of ~20 non-fleet
     repos found referencing a service this way, only about half did so from
     application code; the rest were deployment manifests, env files and
     READMEs, correctly ignorable. Cloning on a raw match would roughly double
     the fleet with the wrong half.

Evidence kind is `textual`: an org-wide match on a service name is strong for
"this repo talks to that service" and silent on which shape it deserializes.

Usage:
  forge_gaps.py <fleet-root> <query> [--org NAME] [--limit N]
Exit: 0 gaps found, 1 no repo beyond the fleet matches, 3 no org could be
      determined, 4 the forge search did not run (never an empty answer).
"""
import collections
import json
import os
import pathlib
import re
import subprocess
import sys

FORGE_BIN = os.environ.get("CS_FORGE_BIN", "gh")

# Paths that reference a service without calling it. A match here says the repo
# deploys or documents the thing, not that it has a client for it -- a different
# finding, and the one that must not drive a clone.
CONFIG_ONLY_SUFFIXES = {
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".env", ".md", ".markdown", ".rst", ".txt", ".tf", ".tfvars", ".lock",
}
CONFIG_ONLY_NAMES = {
    "dockerfile", "makefile", "procfile", "readme", "changelog", ".gitignore",
}
CONFIG_ONLY_DIRS = ("deploy/", "deployment/", "k8s/", "kubernetes/", "helm/",
                    "charts/", "manifests/", "terraform/", ".github/", "docs/")


def classify(path):
    p = path.lower()
    base = p.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0]
    suffix = "." + base.rsplit(".", 1)[-1] if "." in base else ""
    if base in CONFIG_ONLY_NAMES or stem in CONFIG_ONLY_NAMES:
        return "config"
    if any(p.startswith(d) or ("/" + d) in p for d in CONFIG_ONLY_DIRS):
        return "config"
    if suffix in CONFIG_ONLY_SUFFIXES:
        return "config"
    return "code"


def fleet_repos(root):
    return {d.name for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".")}


def org_of(root):
    """The owner most of the fleet's remotes point at, or None.

    Read from the repos themselves rather than configured separately: the fleet
    IS the sample, and a fleet whose remotes disagree is exactly the case where
    guessing one owner would search the wrong org.
    """
    owners = collections.Counter()
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            out = subprocess.run(
                ["git", "-C", str(d), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode != 0:
            continue
        url = out.stdout.strip()
        # A FORGE remote only. A local-path remote (`/srv/mirrors/foo.git`, and
        # every fixture fleet) would otherwise yield a directory name as the
        # "org" -- and searching a nonsense org returns zero results, which this
        # verb would then report as "nothing beyond the fleet". That is the
        # false negative the whole file exists to prevent, arriving through its
        # own configuration.
        m = re.match(
            r"^(?:https?://|ssh://)?(?:[^@/]+@)?"      # scheme and user
            r"(?P<host>[A-Za-z0-9._-]+\.[A-Za-z]{2,})"  # a real hostname
            r"[:/](?P<owner>[^/:]+)/[^/]+?(?:\.git)?/?$", url)
        if m:
            owners[m.group("owner")] += 1
    return owners.most_common(1)[0][0] if owners else None


def search(org, query, limit):
    """Rows from the forge, or None with a reason. NEVER an empty list on error."""
    cmd = [FORGE_BIN, "search", "code", query, "--owner", org,
           "--json", "path,repository", "--limit", str(limit)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        return None, f"{FORGE_BIN} is not installed"
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"{FORGE_BIN} could not be run: {e}"
    # Rule 1. stderr is READ, not suppressed, and a non-zero status is a refusal.
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip().splitlines()
        tail = " ".join(detail[-3:]) if detail else "(no output)"
        return None, f"{FORGE_BIN} exited {p.returncode}: {tail}"
    try:
        rows = json.loads(p.stdout or "[]")
    except ValueError:
        return None, (f"{FORGE_BIN} exited 0 but its output is not JSON, so "
                      f"nothing was read: {(p.stdout or '')[:200]!r}")
    if not isinstance(rows, list):
        return None, f"{FORGE_BIN} returned JSON that is not a list of results"
    return rows, None


def main():
    args = [a for a in sys.argv[1:]]
    org = None
    limit = 100
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--org" and i + 1 < len(args):
            org = args[i + 1]; i += 2
        elif args[i].startswith("--org="):
            org = args[i].split("=", 1)[1]; i += 1
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i].startswith("--limit="):
            limit = int(args[i].split("=", 1)[1]); i += 1
        else:
            rest.append(args[i]); i += 1
    if len(rest) < 2:
        print(__doc__, file=sys.stderr)
        return 4
    root, query = pathlib.Path(rest[0]), rest[1]
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 4

    org = org or os.environ.get("CS_ORG") or org_of(root)
    if not org:
        print("no organisation could be determined: no repo in the fleet has an "
              "origin remote pointing at a forge host. A local-path remote is "
              "deliberately not read as an org -- searching a nonsense org "
              "returns zero, which would be reported as 'nothing beyond the "
              "fleet'. Pass --org, or set CS_ORG.", file=sys.stderr)
        return 3

    rows, err = search(org, query, limit)
    if rows is None:
        # Refusal, never a zero. See rule 1 in the module docstring.
        print(f"the org-wide search did not run: {err}", file=sys.stderr)
        return 4

    fleet = fleet_repos(root)
    beyond = collections.defaultdict(lambda: {"code": [], "config": []})
    in_fleet = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        repo = (r.get("repository") or {}).get("nameWithOwner") or ""
        name = repo.split("/")[-1]
        path = r.get("path") or ""
        if not name or not path:
            continue
        if name in fleet:
            in_fleet.add(name)
            continue
        beyond[name][classify(path)].append(path)

    print(f"org: {org}   fleet: {len(fleet)} repo(s)   "
          f"matched in fleet: {len(in_fleet)}", file=sys.stderr)

    if not beyond:
        print(f"no repo beyond the fleet matches '{query}' in {org} — a "
              f"fleet-scoped negative for this query is not bounded by anything "
              f"this found, within the first {limit} result(s)", file=sys.stderr)
        return 1

    n_code = 0
    for name in sorted(beyond):
        kinds = beyond[name]
        kind = "application code" if kinds["code"] else "config only"
        if kinds["code"]:
            n_code += 1
        sample = (kinds["code"] or kinds["config"])[0]
        print(f"{name}: {sample}   [{kind}, "
              f"{len(kinds['code']) + len(kinds['config'])} hit(s)]")

    print(f"a fleet-scoped negative for '{query}' is bounded by the "
          f"{len(beyond)} repo(s) above, {n_code} of them from application code",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
