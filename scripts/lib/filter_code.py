#!/usr/bin/env python3
"""Drop matches that sit inside a comment or docstring.

Reads `path:line: text` on stdin and writes back only the lines whose match is
in executable code. This is the one thing no single engine did well: ripgrep
counts a docstring mentioning an endpoint as a caller, and a symbol graph
cannot see the string literal that is the real call site.

Line-leading markers are not enough -- a docstring's middle line carries no
marker at all -- so this tracks block state by scanning each file once.

Usage: filter_code.py [--invert] [--root DIR]
"""
import sys
import pathlib
import argparse
from functools import lru_cache

LINE_COMMENT = {
    ".py": ("#",), ".rb": ("#",), ".sh": ("#",), ".yml": ("#",), ".yaml": ("#",),
    ".cs": ("//",), ".kt": ("//",), ".kts": ("//",), ".java": ("//",),
    ".ts": ("//",), ".tsx": ("//",), ".js": ("//",), ".jsx": ("//",),
    ".go": ("//",), ".rs": ("//",),
}
BLOCK = {
    ".cs": [("/*", "*/")], ".kt": [("/*", "*/")], ".kts": [("/*", "*/")],
    ".java": [("/*", "*/")], ".ts": [("/*", "*/")], ".tsx": [("/*", "*/")],
    ".js": [("/*", "*/")], ".jsx": [("/*", "*/")], ".go": [("/*", "*/")],
    ".rs": [("/*", "*/")],
    ".py": [('"""', '"""'), ("'''", "'''")],
}


@lru_cache(maxsize=512)
def comment_lines(path_str):
    """Return the set of 1-based line numbers that are comment or docstring."""
    path = pathlib.Path(path_str)
    ext = path.suffix
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return frozenset()

    out = set()
    open_marker = None
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()

        if open_marker is not None:
            out.add(idx)
            if open_marker[1] in raw:
                open_marker = None
            continue

        for start, end in BLOCK.get(ext, []):
            pos = raw.find(start)
            if pos == -1:
                continue
            # Ignore a delimiter that is itself inside a normal string on the line.
            out.add(idx)
            rest = raw[pos + len(start):]
            if end not in rest:
                open_marker = (start, end)
            break
        else:
            for marker in LINE_COMMENT.get(ext, ()):
                if line.startswith(marker):
                    out.add(idx)
                    break
    return frozenset(out)


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--invert", action="store_true",
                    help="keep only the comment matches instead")
    ap.add_argument("--root", default=".")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()
    if args.help:
        print(__doc__)
        return 0

    root = pathlib.Path(args.root)
    for raw in sys.stdin:
        line = raw.rstrip("\n")
        parts = line.split(":", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            print(line)          # not a match line; pass through untouched
            continue
        rel, num = parts[0], int(parts[1])
        in_comment = num in comment_lines(str(root / rel))
        if in_comment == args.invert:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
