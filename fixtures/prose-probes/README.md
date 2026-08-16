# Prose-filter probes

One file per language, each carrying exactly two tokens:

- `cs-probe-<lang>-PROSE` — appears **only** inside comments
- `cs-probe-<lang>-CODE` — appears **only** in executable code

`cs uses` must find every `-CODE` token and no `-PROSE` token. That is the whole
assertion, and it is a pair rather than a single check on purpose: testing only
that the prose token is absent passes just as happily when `cs uses` is broken
and finds nothing at all, which is a false pass that actually happened.

## Why these live outside `fixtures/repos/`

The five repos in `fixtures/repos/` are a modelled system — a .NET API, a Kotlin
caller, a Python worker, a TypeScript monorepo, a Java library — with planted
seams and decoys documented in `GROUND-TRUTH.md`, and `BASELINE.md` records how
each engine scores against them. Adding languages there would mean either
inventing services nobody would build to host them, or perturbing the nine
scored queries and the baseline that interprets them.

These probes are not a system. They are a table of comment syntaxes. So
`verify-search` copies them into a throwaway repo inside the fixture fleet at
test time and removes them afterwards, and the demo fleet stays the five repos
it has always been.

## Why the coverage matters

`scripts/lib/filter_code.py` recognises comments by file extension. An extension
it does not know gets an empty comment set, which means every line counts as
code — so `cs uses` silently degrades to `cs seam` for that language while still
reporting `prose filtered`. The failure is invisible to anyone whose fleet is
written in the languages already covered, which is exactly why the fixture stack
alone could not catch it: C#, Kotlin, Python, TypeScript and Java were all
supported from the start.

A hit in a genuinely unsupported language is now passed through **and named** in
the answer line (`prose filtered except: .foo`), rather than silently included
under a claim that did not hold.

## Adding a language

Drop in `probe.<ext>` with the two tokens, following the pattern above. Nothing
else needs changing — `verify-search` discovers the files and derives the token
names from them. A language whose probe fails is either missing from
`LINE_COMMENT`/`BLOCK` in `filter_code.py`, or is there with the wrong markers.
