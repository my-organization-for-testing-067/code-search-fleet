#!/usr/bin/env python3
"""Ask a tokensave graph what implements a type, in cs's line format.

Why this exists: the `resolved` tier needs a language server, and a language
server needs its language's toolchain. For .NET Framework C# that toolchain is
Windows-only to build, so on macOS or Linux `resolved` is unavailable BY
CONSTRUCTION -- not for want of installing something. Without a fallback, cs has
no answer at all for "what implements this interface" in those repos.

A prebuilt graph is the profile the facade is otherwise missing: offline,
cross-repo, and needing no per-language toolchain.

Three traps, all reproduced against tokensave 7.9.0 rather than taken on trust:

  1. The hierarchy tool takes a NODE ID, not a name. `type_hierarchy` rejects a
     bare name loudly ("node not found"), but the related `callers_for` accepts
     one and returns an empty result with exit 0 -- indistinguishable from
     "nothing implements this", which is the manufactured negative cs refuses to
     emit. So the lookup is two-step (search -> id -> hierarchy), and a symbol
     that cannot be resolved to a type node exits 3 rather than printing nothing.
  2. `tokensave tool ...` accepts `--project <dir>`; `tokensave status` takes its
     path POSITIONALLY and rejects `--project`. Both spellings are used below,
     each where it works.
  3. A graph answers about the code as of its last sync, so it is the one engine
     here that can be confidently WRONG rather than merely blind. Staleness is
     surfaced by the caller; see `cs engines`.

Usage: tokensave_call.py <impls|def> <repo-dir> <repo-name> <symbol>
Exit:  0 found, 1 nothing found (an honest negative), 3 symbol not resolvable
       as a type (impls only), 4 the tool itself failed.
"""
import json
import re
import subprocess
import sys

# `Name (kind) -- path:line`, with the edge kind on the indented rows.
ROW = re.compile(r"^\|-\s+(\w+)\s+(.+?)\s+\((\w+)\)\s+--\s+(.+):(\d+)\s*$")

TYPE_KINDS = ("interface", "class", "trait", "struct", "enum", "record", "type")

# `search` is a RANKED, fuzzy match, so `Reserve` also returns ReserveAsync,
# ReservationController and ReserveRequest. cs def answers "where is this symbol
# defined", so only an exact name counts -- and these kinds are references or
# containers rather than definitions, which ctags would not report either.
NOT_A_DEFINITION = ("use", "annotation_usage", "file")


def _run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"tokensave could not be run: {e}"
    if p.returncode != 0:
        return None, (p.stderr or p.stdout or "").strip()[:300]
    return p.stdout, None


def _search(project, symbol, limit):
    out, err = _run(["tokensave", "tool", "search", symbol,
                     "--project", project, "--limit", str(limit)])
    if out is None:
        print(f"tokensave search failed: {err}", file=sys.stderr)
        return None
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        print("tokensave search returned no parseable JSON", file=sys.stderr)
        return None
    if not isinstance(rows, list):
        rows = rows.get("results", []) if isinstance(rows, dict) else []
    return [r for r in rows if isinstance(r, dict)]


def defs(project, repo, symbol):
    """Where a symbol is DEFINED, as a cross-repo alternative to the ctags index."""
    rows = _search(project, symbol, 100)
    if rows is None:
        return 4
    found = 0
    for r in rows:
        if r.get("name") != symbol:
            continue
        kind = r.get("kind", "?")
        if kind in NOT_A_DEFINITION:
            continue
        if not r.get("file"):
            continue
        print(f"{repo}/{r['file']}:{r.get('line', '?')}: [{kind}] {symbol}")
        found += 1
    return 0 if found else 1


def main():
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        return 4
    mode, project, repo, symbol = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    if mode == "def":
        return defs(project, repo, symbol)
    if mode != "impls":
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 4

    # Step 1: resolve the name to a graph node id.
    out, err = _run(["tokensave", "tool", "search", symbol, "--project", project])
    if out is None:
        print(f"tokensave search failed: {err}", file=sys.stderr)
        return 4
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        print("tokensave search returned no parseable JSON", file=sys.stderr)
        return 4
    if not isinstance(rows, list):
        rows = rows.get("results", []) if isinstance(rows, dict) else []

    node = next(
        (r for r in rows
         if isinstance(r, dict)
         and r.get("name") == symbol
         and r.get("kind") in TYPE_KINDS),
        None,
    )
    if not node or not node.get("id"):
        # NOT an empty answer. The graph was never asked the question, so
        # printing nothing here would be a negative nobody established.
        print(f"tokensave: '{symbol}' is not a type node in this graph",
              file=sys.stderr)
        return 3

    # Step 2: the hierarchy, by id.
    out, err = _run(["tokensave", "tool", "type_hierarchy",
                     "--node-id", node["id"], "--project", project])
    if out is None:
        print(f"tokensave type_hierarchy failed: {err}", file=sys.stderr)
        return 4

    found = 0
    for line in out.splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        edge, name, kind, path, lineno = m.groups()
        # `implements` and `extends` both, which is the whole point: C# has one
        # syntax for both relations, so an extractor that resolves some names
        # and defaults the rest files interface implementations under either.
        # The edge kind is printed so the reader can see which it was.
        print(f"{repo}/{path}:{lineno}: [{kind}] {name} ({edge})")
        found += 1

    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
