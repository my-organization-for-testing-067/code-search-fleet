---
name: code-search
description: Search across many repositories at once — find who calls an endpoint, where a symbol is defined, what implements an interface, or which repo publishes a package. Use whenever a question spans more than one repo, or when grep alone gives noisy or incomplete answers. Trigger phrases: "who calls", "where is X defined", "what implements", "across the repos", "which repo", "find usages", "is this endpoint dead", "impact of changing".
---

# Searching a fleet of repositories

Use `scripts/cs`. It is one interface over five engines, because **no single
engine answers every question** — measured, not assumed: across nine scored
queries the best individual engine got 5/9, and `cs` gets 9/9.

Do not reach for raw `grep` first. It cannot see a route assembled from two C#
attributes, it counts a docstring mentioning an endpoint as a caller, and it
cannot resolve an interface to its implementation.

## Setup

```sh
scripts/bootstrap           # installs the engines; --check to only report
export FLEET_ROOT=~/code/fleet   # the directory holding all the repos
```

Every engine is optional. `cs engines` reports what is present, and `cs` routes
around whatever is missing rather than failing silently.

## Which subcommand

Run `cs which` for this table at any time.

| What you want to know | Use |
|---|---|
| Who calls/uses this endpoint, topic, config key | `cs uses <string>` |
| Which repos share this string | `cs seam <string>` |
| Any text or regex, comments included | `cs text <pattern>` |
| Where a symbol is defined | `cs def <symbol> [repo]` |
| Calls shaped like X, or taking literal Y | `cs calls '<pattern>' [lang]` |
| What implements this interface | `cs impls <symbol> <repo>` |
| What references this symbol (bridges DI) | `cs refs <symbol> <repo> <file>` |
| Which repo publishes this package | `cs provides <coordinate>` |
| Which repos depend on which | `cs deps [repo]` |

**Start cheap.** `cs uses`, `cs def`, and `cs seam` answer in well under a
second. `cs impls` and `cs refs` start language servers and take minutes on a
large repo — reach for them when you need symbol-level truth, not for a first
look.

When a subcommand finds nothing it prints what to try instead, so a wrong first
choice self-corrects.

## The distinctions that matter

**`cs uses` vs `cs seam` vs `cs text`.** All three search strings, but:
`cs text` returns everything including comments; `cs seam` groups by repo and
warns when only one repo mentions a string (the shape of a dead endpoint or an
orphaned consumer); `cs uses` excludes comments and docstrings, so it answers
"who actually calls this" rather than "who mentions this". For "is this
endpoint still used", `cs uses` is the right one and the other two will mislead
you.

**Two same-named symbols in different repos.** Code search cannot tell them
apart — the answer is in build manifests, not code. Resolve the dependency
first, then filter:

```sh
cs def DiscountEngine "$(cs provides com.acme:pricing-lib)"
```

## Known blind spots — do not oversell an answer

- **Cross-repo, cross-language relations are strings.** A Kotlin service calling
  a .NET endpoint is connected only by the route literal. `cs uses` finds those
  seams; nothing resolves them symbolically. Say so rather than implying a
  verified call graph.
- **Runtime indirection defeats static analysis.** DI registration, reflection,
  and dynamically built identifiers are invisible. `cs refs` bridges DI
  *registration* because a language server sees the type arguments, but a
  container resolving by string name is beyond every tool here. The honest
  answer names the interface and says the implementation is resolved at runtime.
- **`cs def` uses ctags**, which indexes declarations, not semantics. It will
  not find a symbol assembled at runtime, and it does not distinguish
  overloads. `cs refs` is the precise-but-slow alternative.
- **A clean result is not proof of absence.** For "is this dead", check with
  `cs uses` *and* `cs seam` before concluding, since a caller may construct the
  string rather than write it literally.

## Verifying it works

The repo ships a fixture fleet with known-correct answers, including decoys
designed to catch over-eager tools:

```sh
scripts/build-fixtures /tmp/fixture-fleet
export FLEET_ROOT=/tmp/fixture-fleet
cs uses "/api/v1/inventory/reserve" | scripts/score-seams reserve-consumers -
```

`scripts/score-seams --list` shows all nine queries. `fixtures/BASELINE.md`
records how each engine scores alone, and `fixtures/GROUND-TRUTH.md` explains
what each query is testing. Use these to check a change to the search setup
before trusting it.

## Reporting results

Give file paths as `repo/path:line`, which is the format `cs` already emits and
which stays clickable. When an answer rests on a string match across a repo
boundary, say that — the reader needs to know it is a textual link and not a
resolved reference.
