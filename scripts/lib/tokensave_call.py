#!/usr/bin/env python3
"""Ask a tokensave graph a symbol question, in cs's line format.

Why this exists: the `resolved` tier needs a language server, and a language
server needs its language's toolchain. For .NET Framework C# that toolchain is
Windows-only to build, so on macOS or Linux `resolved` is unavailable BY
CONSTRUCTION -- not for want of installing something. Without a fallback, cs has
no answer at all for "what implements this interface" in those repos.

A prebuilt graph is the profile the facade is otherwise missing: offline,
cross-repo, and needing no per-language toolchain.

Four traps, all reproduced against tokensave 7.9.0 rather than taken on trust:

  1. The graph tools take a NODE ID, not a name, and they DISAGREE about what to
     do with a name. `type_hierarchy`, `callers` and `callees` reject a bare name
     loudly ("node not found", exit 1). `callers_for` and `impact` accept one and
     succeed while having looked nothing up:

         tokensave tool callers_for <Name>  -> {"callers": {"<Name>": []}}, exit 0
         tokensave tool impact      <Name>  -> {"node_count": 0, ...},      exit 0

     That is a manufactured negative -- "nothing calls this" is exactly the
     answer someone deletes code on. So every lookup here is two-step
     (name -> node id -> the real question), and a symbol that does not resolve
     to a node exits 3 rather than printing nothing. A well-formed id with
     genuinely no edges also returns empty, and nothing at the call site can
     tell that apart from the bug; only the two-step makes the empty trustworthy.
  2. `tokensave tool ...` accepts `--project <dir>`; `tokensave status` takes its
     path POSITIONALLY and rejects `--project`. Both spellings are used below,
     each where it works.
  3. A graph answers about the code as of its last sync, so it is the one engine
     here that can be confidently WRONG rather than merely blind. Staleness is
     surfaced by the caller; see `cs engines`.
  4. One name is often several nodes -- an interface method and its
     implementation both answer to `ReserveAsync`. Asking only the top-ranked one
     reported "nothing calls ReserveAsync" when the implementation had a caller
     and the interface method did not. Every exact-name node is asked, and the
     set is named on stderr so the reader can see what was actually queried.

Usage: tokensave_call.py <impls|def|callers|callees|impact|fields> <repo-dir>
                         <repo-name> <symbol>
Exit:  0 found, 1 nothing found (an honest negative), 3 the symbol does not
       resolve to a node this question can be asked of, 4 the tool itself failed.
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

# What can appear at either end of a `calls` edge, across the languages the
# fixture fleet covers (C#, Java, Kotlin, TypeScript, Python).
CALLABLE_KINDS = ("function", "method", "constructor", "abstract_method")

# Containers: a class HAS callers in no sense the call graph records, so asking
# for them would produce an empty result that reads as "nothing calls this".
# That is the one answer this file exists to never manufacture, so a name that
# resolves ONLY to these is refused with the question it should have been.
# A kind in neither list is asked anyway -- a TypeScript `const` can hold an
# arrow function -- because the two-step has already happened by then and the
# node's kind is printed next to every row.
CONTAINER_KINDS = ("class", "interface", "trait", "struct", "enum", "record",
                   "data_class", "kotlin_object", "namespace", "package",
                   "module", "kotlin_package", "type")

# How far `impact` walks. Pinned rather than left to the tool's default, because
# cs states the depth in its provenance line and a claim that tracks a default
# is a claim that changes when someone else changes theirs.
IMPACT_DEPTH = "3"


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


def _exact_nodes(project, symbol):
    """Every node whose name is EXACTLY the symbol, or None if nothing ran.

    `find_exact_symbol` is an index probe with no ranking and a 200-row cap;
    `search` is BM25 with a default limit of TEN, so on a real repo the node you
    asked about can rank below ten near-misses and simply not be in the list --
    which would arrive here as "this symbol is not in the graph". The ranked
    search is kept only as the fallback for a tokensave without the exact tool.
    """
    out, _ = _run(["tokensave", "tool", "find_exact_symbol", "--name", symbol,
                   "--project", project, "--limit", "200"])
    if out is not None:
        try:
            doc = json.loads(out)
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, dict) and isinstance(doc.get("matches"), list):
            return [m for m in doc["matches"]
                    if isinstance(m, dict) and m.get("id")]
    rows = _search(project, symbol, 200)
    if rows is None:
        return None
    return [r for r in rows if r.get("name") == symbol and r.get("id")]


def _seeds(project, symbol, mode):
    """The nodes to ask `mode` about: (nodes, exit-code). nodes is None on 3/4."""
    nodes = _exact_nodes(project, symbol)
    if nodes is None:
        return None, 4
    nodes = [n for n in nodes if n.get("kind") not in NOT_A_DEFINITION]
    if not nodes:
        # NOT an empty answer. The graph was never asked the question.
        print(f"tokensave: '{symbol}' is not a node in this graph — nothing was "
              f"looked up, so nothing was ruled out", file=sys.stderr)
        return None, 3

    if mode != "impact":
        callable_nodes = [n for n in nodes if n.get("kind") in CALLABLE_KINDS]
        if callable_nodes:
            nodes = callable_nodes
        elif all(n.get("kind") in CONTAINER_KINDS for n in nodes):
            kinds = ", ".join(sorted({n.get("kind", "?") for n in nodes}))
            print(f"tokensave: '{symbol}' resolves only to {kinds} node(s), and "
                  f"a call graph records no calls to or from those — so this is "
                  f"a question the graph cannot be asked, not 'nothing calls it'",
                  file=sys.stderr)
            return None, 3

    if len(nodes) > 1:
        where = ", ".join(f"{n.get('file', '?')}:{n.get('line', '?')}"
                          for n in nodes)
        print(f"tokensave: '{symbol}' is {len(nodes)} nodes in this graph and "
              f"ALL were asked ({where}) — the rows below are their union",
              file=sys.stderr)
    return nodes, 0


def _rows(project, node, mode):
    """The answer rows for one seed node, or None if the tool itself failed."""
    args = ["tokensave", "tool", mode, "--node-id", node["id"],
            "--project", project]
    if mode == "impact":
        args += ["--max-depth", IMPACT_DEPTH]
    else:
        # Depth 1, deliberately. `callees` defaults to 3 and its rows carry no
        # depth field, so the default answer mixes "this function calls it" with
        # "something three hops down does" and gives the reader no way to tell.
        args += ["--max-depth", "1"]
    out, err = _run(args)
    if out is None:
        print(f"tokensave {mode} failed: {err}", file=sys.stderr)
        return None
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        print(f"tokensave {mode} returned no parseable JSON", file=sys.stderr)
        return None
    if mode == "impact":
        return doc.get("nodes", []) if isinstance(doc, dict) else []
    return doc if isinstance(doc, list) else []


def graph_edges(project, repo, symbol, mode):
    """cs callers / cs callees / cs impact, as `repo/path:line: text` lines."""
    nodes, rc = _seeds(project, symbol, mode)
    if nodes is None:
        return rc

    seen, no_location = set(), 0
    seed_ids = {n["id"] for n in nodes}
    for node in nodes:
        rows = _rows(project, node, mode)
        if rows is None:
            return 4
        for r in rows:
            if not isinstance(r, dict):
                continue
            # impact reports the radius INCLUDING the node you asked about, and
            # "X depends on X" is not an answer to "what breaks if I change it".
            if mode == "impact" and r.get("id") in seed_ids:
                continue
            if not r.get("file"):
                no_location += 1
                continue
            if mode == "impact":
                edge = f"depends on {symbol}"
            else:
                edge = r.get("edge_kind") or "calls"
                # The graph resolved this through an interface rather than
                # seeing the call site name the concrete method. Worth printing:
                # it is the one place a graph edge is an inference.
                if r.get("dispatch_via_trait"):
                    edge += ", via the interface"
            line = (f"{repo}/{r['file']}:{r.get('line', '?')}: "
                    f"[{r.get('kind', '?')}] {r.get('name', '?')} ({edge})")
            if line not in seen:
                seen.add(line)
                print(line)

    if no_location:
        # Named rather than dropped: a row cs cannot place is a row cs cannot
        # show, and a quietly shorter answer is a quietly wrong one.
        print(f"tokensave: {no_location} matching node(s) had no file location "
              f"in the graph and are not listed below", file=sys.stderr)
    return 0 if seen else 1


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



# `tokensave tool` truncates its own stdout at 15000 characters -- it is built
# for MCP token budgets, and the cut lands mid-token, leaving INVALID JSON
# rather than a short answer. Measured: ~200 bytes per site, so this trips at
# roughly 75 sites and the reported 160-site case would hit it every time.
#
# `--limit N` bounds read_sites only; write_sites is never capped by it. That
# asymmetry decides the ladder below -- reads can be sacrificed to get an
# answer, writes cannot, and if the writes alone overflow there is nothing
# trustworthy to return.
#
# The cost of using --limit is that `read_count` comes back as the CAPPED
# number, not the true one, so the true read total is unrecoverable. That is
# disclosed rather than papered over: a read total that silently reads as
# complete would understate a blast radius, which is the failure this verb
# exists to prevent.
TRUNCATION_MARK = "[... truncated at"
READ_LIMITS = (None, 30, 10, 1)


def _field_doc(project, field):
    """(doc, applied_read_limit) -- or (None, reason) if nothing usable came back.

    applied_read_limit is None when the full answer parsed, and an int when
    reads had to be capped to make the output fit.
    """
    for limit in READ_LIMITS:
        args = ["tokensave", "tool", "field_sites", "--field", field,
                "--project", project]
        if limit is not None:
            args += ["--limit", str(limit)]
        out, err = _run(args)
        if out is None:
            return None, err
        try:
            doc = json.loads(out)
        except json.JSONDecodeError:
            # Only the engine's own truncation is worth retrying smaller. Any
            # other unparseable output is a different fault and is reported as
            # one rather than retried three more times.
            if TRUNCATION_MARK in out:
                continue
            return None, "returned no parseable JSON"
        if not isinstance(doc, dict):
            return None, "returned JSON that is not an object"
        return doc, limit
    return None, "truncated"


def field_sites(project, repo, field):
    """cs fields: read and write sites of a named field, as cs result lines.

    Emitted as `repo/path:line: [write] snippet` / `[read] snippet` -- the cs
    line shape, with the access kind where the node kind goes for the other
    modes. Nothing is capped here: the caller caps the two kinds SEPARATELY,
    which it can only do if it is handed both in full.

    Exit: 0 sites found, 1 no sites at all, 3 a qualifier that was not applied,
    4 the tool failed, 5 sites found but the engine truncated its own output so
    the reads are a sample. `1` is deliberately NOT treated as an answer by the
    caller -- see below.
    """
    doc, read_limit = _field_doc(project, field)
    if doc is None:
        # read_limit carries the reason when doc is None.
        if read_limit == "truncated":
            print("tokensave truncated its own output at 15000 characters even "
                  "with reads limited to 1, so the WRITE list alone overflows "
                  "and no complete list can be read from this graph",
                  file=sys.stderr)
            return 4
        print(f"tokensave field_sites failed: {read_limit}", file=sys.stderr)
        return 4

    # A `Type::field` query is PARSED into a qualifier and then, on tokensave
    # 7.9.0, not applied -- `qualifier_applied` came back false for every real
    # type probed, in C# and in Python. The results returned are the bare-name
    # results, so a caller who qualified because the bare name was ambiguous
    # gets the ambiguous answer back while believing it was narrowed.
    #
    # Measured, not assumed: `DiscountEngine::_threshold` (a real class) and
    # `NoSuchClass::_threshold` (a fabricated one) returned identical sites and
    # identical counts. A wrong type name is not an error here, so the
    # qualifier cannot even be used as a spell-check.
    #
    # So a qualified query whose qualifier was dropped is refused rather than
    # answered. Answering would return the broader question's result under the
    # narrower question's heading, and the caller asked to narrow precisely
    # because they did not want that. If a later tokensave applies it, this
    # path simply stops triggering.
    if doc.get("qualifier") and not doc.get("qualifier_applied"):
        print(f"tokensave: the qualifier '{doc['qualifier']}' was parsed but "
              f"NOT applied, so these would be the results for the bare field "
              f"name '{doc.get('field', field).split('::')[-1]}' — the broad "
              f"answer under a narrow heading", file=sys.stderr)
        return 3

    found = 0
    # write before read: the two have different blast radii and the writes are
    # the smaller, more surprising set. Within a kind, source order.
    for kind in ("write", "read"):
        seen = set()
        for r in doc.get(f"{kind}_sites") or []:
            if not isinstance(r, dict) or not r.get("file"):
                continue
            # tokensave lists one entry per REFERENCE, so two mentions of the
            # field on one line arrive as two identical entries (measured:
            # read_count 3 over 2 distinct lines). In cs's line format those
            # would print as duplicate rows, which reads as a display bug --
            # and would inflate the hit count the caller weighs the answer by.
            key = (r["file"], r.get("line"), kind)
            if key in seen:
                continue
            seen.add(key)
            snippet = " ".join((r.get("snippet") or "").split())
            # The graph's `enclosing` is `file::file::Class::Member`; only the
            # last two carry information the path does not already give.
            enclosing = "::".join(
                [x for x in (r.get("enclosing") or "").split("::") if x][-2:])
            where = f" in {enclosing}" if enclosing else ""
            print(f"{repo}/{r['file']}:{r.get('line', '?')}: "
                  f"[{kind}]{where} {snippet}")
            found += 1
    if not found:
        return 1
    if read_limit is not None:
        # Exit 5, not 0: the caller has to mark this PARTIAL, and a warning on
        # stderr alone would be a fact the porcelain envelope does not carry.
        print(f"tokensave: output was truncated by the engine, so reads were "
              f"re-requested with --limit {read_limit}. The read sites below "
              f"are a SAMPLE and the true read total is not recoverable from "
              f"this graph; the write list is complete.", file=sys.stderr)
        return 5
    return 0


def main():
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        return 4
    mode, project, repo, symbol = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    if mode == "def":
        return defs(project, repo, symbol)
    if mode == "fields":
        return field_sites(project, repo, symbol)
    if mode in ("callers", "callees", "impact"):
        return graph_edges(project, repo, symbol, mode)
    if mode != "impls":
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 4

    # Step 1: resolve the name to a graph node id. Through the exact-name probe
    # rather than the ranked search this used to call with its default limit of
    # ten -- on a repo where ten near-misses outrank the interface, that reported
    # "not a type node in this graph" about a type that is right there.
    rows = _exact_nodes(project, symbol)
    if rows is None:
        return 4

    node = next(
        (r for r in rows if r.get("kind") in TYPE_KINDS),
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
