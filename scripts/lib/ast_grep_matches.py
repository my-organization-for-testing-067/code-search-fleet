#!/usr/bin/env python3
"""Turn `ast-grep --json=stream` into `path:line:source-line`, keeping only the
matches that actually contain the literal the pattern was built around.

Why this exists rather than reading ast-grep's plain output directly:

A pattern like `new Widget($$$ARGS)` is parsed once PER LANGUAGE, and a grammar
that cannot express the shape does not reject the pattern -- it parses it into
whatever nodes it does have. In a loosely-parsed language (markdown is the one
that bit us: its inline content is opaque, so the pattern collapses to little
more than "a paragraph with brackets in it") the result is a pattern with the
type name no longer in it, matching prose in every `.md` file in the fleet.
Measured on a 43-repo fleet: a type that exists NOWHERE returned 167 hits, all
markdown, 93% of the answer -- the same 167 the real query returned.

Every construction shape cs searches puts the type name at the START of the
matched region (`new T(`, `T(`, `T.builder(`, `T.m(`), so "the match text
contains the type name" is an invariant the engine is not trusted to keep, and
checking it here discards a degenerate match without touching a real one. It is
a check on the ENGINE, not a relevance filter: a dropped match is one the
pattern's own constraint was silently not applied to.

The check is per MATCH, not per line, which is why the JSON is needed at all --
a multi-line construction has the type name on its first line only, and a
line-wise test would throw the body of every real hit away.

Source lines are read back from disk so the output is the full line the match
sits on, not just the matched region: `z = Widget(` rather than `Widget(`.

usage: ast_grep_matches.py <root> <literal> [<dropped-count-file>]
       ast-grep ... --json=stream | ast_grep_matches.py ...
"""
import json
import os
import sys


def matches(raw):
    """ast-grep emits one JSON object per line under --json=stream, and a single
    JSON array under the older/other --json styles. Accept either, so this does
    not become a version pin on the engine."""
    raw = raw.strip()
    if not raw:
        return
    if raw.startswith("["):
        try:
            for m in json.loads(raw):
                yield m
        except (json.JSONDecodeError, TypeError):
            pass
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    literal = sys.argv[2] if len(sys.argv) > 2 else ""
    dropped_file = sys.argv[3] if len(sys.argv) > 3 else ""

    dropped = 0
    cached_path, cached_lines = None, []

    for m in matches(sys.stdin.read()):
        path = m.get("file") or ""
        text = m.get("text") or ""
        rng = m.get("range") or {}
        start = (rng.get("start") or {}).get("line")
        end = (rng.get("end") or {}).get("line")
        if not path or start is None:
            continue
        if literal and literal not in text:
            dropped += 1
            continue

        if path != cached_path:
            cached_path = path
            try:
                with open(os.path.join(root, path), "r",
                          encoding="utf-8", errors="replace") as fh:
                    cached_lines = fh.read().splitlines()
            except OSError:
                # The file moved or is unreadable now. The match text is still a
                # true record of what was found, so it is emitted rather than
                # dropped -- silently losing a real hit is the worse failure.
                cached_lines = []

        if end is None:
            end = start
        span = text.splitlines() or [""]
        for i in range(start, end + 1):
            if i < len(cached_lines):
                body = cached_lines[i]
            else:
                body = span[i - start] if i - start < len(span) else ""
            print("%s:%d:%s" % (path, i + 1, body))

    if dropped_file:
        try:
            with open(dropped_file, "a", encoding="utf-8") as fh:
                fh.write("%d\n" % dropped)
        except OSError:
            pass


if __name__ == "__main__":
    main()
