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
| When a seam appeared, or last changed | `cs history <string> [repo]` |
| What is actually being searched right now | `cs repos` |

**Start cheap.** `cs uses`, `cs def`, and `cs seam` answer in well under a
second. `cs impls` and `cs refs` start language servers and take minutes on a
large repo — reach for them when you need symbol-level truth, not for a first
look.

When a subcommand finds nothing it prints what to try instead, so a wrong first
choice self-corrects.

## Read the answer kind before you trust the answer

Every result ends with a line naming the kind of evidence behind it:

```
answer: heuristic via ripgrep (literal, prose filtered) · 2 hit(s) · 2 repo(s)
```

The kind matters most for **negative** results, which is where a search tool
does real damage — concluding "nothing uses this" is what makes a breaking
change look safe.

| Kind | From | A negative result means |
|---|---|---|
| `resolved` | serena (LSP) | strong: no reference — within that one repo |
| `declared` | build manifests | strong: not declared |
| `historical` | `git log -S`/`-G` | strong, for tracked files |
| `structural` | ast-grep / semgrep / ctags | medium: no such syntax shape |
| `heuristic` | text match, prose filtered | **weak** |
| `textual` | ripgrep / grep | **weakest** — an occurrence is not a use |

`cs why <kind>` prints exactly what that kind cannot see; `--why` on any query
gives it inline.

Three warnings `cs` emits that you must pass on rather than swallow:

- **`PARTIAL`** — an engine hit its timeout, so the result is a subset, not an
  answer. Raise `CS_TIMEOUT` and rerun before concluding anything from it.
- **`showing N of M`** — capped at 200 results. The per-repo distribution of all
  M is printed; use it to narrow, or pass `--all`.
- **`degraded:`** — an engine was missing and `cs` fell back to another with a
  different pattern dialect. The results are not equivalent.

## Finding a cause in another repo

When something breaks and nothing in its own repo changed, the trigger is in a
repo whose history is not reachable from where you are standing. `cs history`
spans the fleet and sorts by date, which puts the two changes side by side:

```sh
cs history 'reservationId'
# 2026-02-17  checkout-service-kotlin   7041e2d  PROJ-388: return the reservation id
# 2026-03-30  inventory-api-dotnet      a41c9e2  Bump serialization settings
```

It uses git's pickaxe (`-S`), which reports commits that changed the *number* of
occurrences — that is what separates the commit which introduced a seam from the
hundreds that merely touched the file. A change made **in place** leaves the
count identical and is invisible to `-S`, which is exactly the shape of a
formatting or serializer change; `cs` escalates to `-G` automatically and says
that it did. `--touched` forces `-G` from the start.

## Two levels: fleet and ticket workspace

The setup is a **fleet** directory holding every repo on main, plus a
**ticket workspace** holding worktrees of just the repos a ticket changes.
Search must span both, and `cs` does this automatically: run it from inside a
ticket workspace and it layers the ticket's repos (your branch state) over the
rest of the fleet (main).

```sh
export FLEET_ROOT=~/code/fleet TICKETS_ROOT=~/tickets
cd ~/tickets/PROJ-123 && cs uses "/api/v1/inventory/reserve"
# searching: PROJ-123 (2 repo(s), your branch) + fleet (8 repo(s), main)
```

This matters more than it sounds. Searching **only** the ticket makes renaming a
shared route look safe, because the caller that breaks lives in a repo the
ticket does not contain. Searching **only** the fleet shows stale copies of the
files you are editing. Both answers are wrong in ways that do not announce
themselves.

- `--fleet` ignores the ticket workspace entirely.
- `--ticket=<id>` layers a named ticket instead of the one you are standing in.

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
- **`grep` may not be the `grep` you tested with.** In an agent shell, `grep`
  and `rg` can be shell functions proxying a bundled ripgrep; a *script* gets
  the real system binary instead. BSD `grep -R` follows a symlink named on the
  command line but not one met while recursing, so a naive recursive search
  over a symlinked view silently finds nothing. `cs` passes repo directories
  explicitly to avoid depending on that behaviour at all — but the lesson
  generalises: verify search changes by running the script, not by running the
  command interactively.
- **A clean result is not proof of absence.** For "is this dead", check with
  `cs uses` *and* `cs seam` before concluding, since a caller may construct the
  string rather than write it literally. The answer kind tells you how much the
  empty result is worth; a `textual` or `heuristic` negative is close to nothing.
- **A structural engine returns nothing for a language it cannot parse**, which
  looks identical to "no matches". Name the language (`cs calls '<pat>' csharp`)
  to turn that silence into an error.

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
what each query is testing.

**Two layers, and you need both:**

```sh
scripts/verify-search     # end-to-end: does the facade still answer all nine?
scripts/verify-engines    # per-engine: is each engine still doing its job?
```

`verify-engines` exists because **the facade hides engine regressions**:
`cs calls` falls back from ast-grep to semgrep, so ast-grep could break
entirely and the end-to-end run would still score 9/9. Each engine is therefore
probed directly on the one capability the routing depends on it for.

Run both after upgrading any tool. `verify-engines` compares against
`fixtures/verified-versions.tsv` and flags version changes as a prompt to look,
not as a failure. `--update` records a new baseline once you have reviewed the
results.

It also probes **known limitations**, not just capabilities. tokensave is
checked for whether its C# `implements` edges have appeared; if a release fixes
that, the probe reports `IMPROVED` and the routing should be reconsidered.
Upgrades can remove the reason a tool was rejected, and nothing else would
notice.

## Reporting results

Give file paths as `repo/path:line`, which is the format `cs` already emits and
which stays clickable.

**Carry the answer kind into what you tell the user.** `cs` prints it precisely
so it does not have to be guessed at: an answer that rests on a string match
across a repo boundary is a textual link, not a resolved reference, and saying
"the only caller is X" on `textual` evidence overstates what was actually
checked. Say which it was, and say when a result was `PARTIAL`, capped, or
`degraded` — a confident summary of an incomplete search is the failure this
whole setup exists to prevent.
