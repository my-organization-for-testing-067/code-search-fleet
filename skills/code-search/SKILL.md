---
name: code-search
description: Search across many repositories at once — find who calls an endpoint, where a symbol is defined, what implements an interface, or which repo publishes a package. Use whenever a question spans more than one repo, or when grep alone gives noisy or incomplete answers. Trigger phrases: "who calls", "where is X defined", "what implements", "across the repos", "which repo", "find usages", "is this endpoint dead", "impact of changing".
---

# Searching a fleet of repositories

Use the `cs` command. It is one interface over five engines, because **no single
engine answers every question** — measured, not assumed: across nine scored
queries the best individual engine got 5/9, and `cs` gets 9/9.

Do not reach for raw `grep` first. It cannot see a route assembled from two C#
attributes, it counts a docstring mentioning an endpoint as a caller, and it
cannot resolve an interface to its implementation.

## Finding the command

The working directory is the user's project, not this tool, so `cs` is never on
a relative path. Resolve it once at the start of the session and reuse it:

```sh
CS="${CLAUDE_PLUGIN_ROOT:-$PWD}/scripts/cs"    # installed as a plugin, or a clone
"$CS" engines
```

`CLAUDE_PLUGIN_ROOT` is set when this is installed as a plugin. From a plain
clone, use the checkout's own path. Every example below writes `cs` for
readability; run `"$CS"`.

## Setup

```sh
"$CS" engines                        # what is installed here
"${CLAUDE_PLUGIN_ROOT:-.}/scripts/bootstrap"   # install missing engines
export FLEET_ROOT=~/code/fleet       # the directory holding all the repos
```

**`FLEET_ROOT` is required** and there is no useful default — without it `cs`
searches the current directory, which is not a fleet. If it is unset, ask the
user for the directory holding their repos rather than guessing.

Every *engine* is optional. `cs engines` reports what is present, and `cs` routes
around whatever is missing rather than failing silently. **`python3` is the
exception** — `uses`, `provides`, `deps`, `publishes`, `impls` and `refs` run
through it, and refuse without it rather than returning zero hits that would
read exactly like a real "nothing uses this". If `cs` reports python3 missing,
tell the user; `cs seam` still works without it, but counts comments as hits.

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
| Which version each repo pins, and where they disagree | `cs versions [coordinate]` |
| Who to ask about this repo or file | `cs owns [repo\|repo/path]` |
| When a seam appeared, or last changed | `cs history <string> [repo]` |
| What is actually being searched right now | `cs repos` |

**Start cheap.** `cs uses`, `cs def`, and `cs seam` answer in well under a
second. `cs impls` and `cs refs` start language servers and take minutes on a
large repo — reach for them when you need symbol-level truth, not for a first
look.

Every subcommand emits the same line format, including the two LSP-backed ones:

```
$ cs refs IInventoryStore inventory-api-dotnet src/Domain/IInventoryStore.cs
inventory-api-dotnet/src/Controllers/ReservationController.cs:9: [Class] private readonly IInventoryStore _store;
inventory-api-dotnet/src/Program.cs:11: [File] builder.Services.AddScoped<IInventoryStore, SqlInventoryStore>();
```

That second hit is the DI registration — the step neither grep nor a call graph
bridges, and the reason `cs refs` is worth its cost.

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

Four warnings `cs` emits that you must pass on rather than swallow:

- **`PARTIAL`** — an engine hit its timeout, so the result is a subset, not an
  answer. Raise `CS_TIMEOUT` and rerun before concluding anything from it.
- **`showing N of M`** — capped at 200 results. The per-repo distribution of all
  M is printed; use it to narrow, or pass `--all`.
- **`degraded:`** — an engine was missing and `cs` fell back to another with a
  different pattern dialect. The results are not equivalent.
- **`prose filtered except: <extensions>`** — `cs uses` met files in a language
  its comment filter does not know, and passed them through unfiltered. Hits in
  those files may be comments. Treat them as `cs seam` hits, not `cs uses` hits.

## When cs refuses, it is protecting you from a false negative

`cs` exits non-zero with an explanation rather than returning an empty result
when it cannot answer honestly: no such fleet root, no repos in it, python3
missing, or `--ticket=<id>` naming a workspace that does not exist. **Do not
work around a refusal by falling back to raw `grep`** — the refusal means the
conditions for a trustworthy negative are not met, and grep's negative is
weaker still. Fix the cause, or tell the user what is missing.

Note the difference between exit codes: a refusal prints an error and explains
what is wrong, while a *successful* query that simply found nothing prints
`0 hit(s)` with an answer-kind label and a "nothing found — try:" hint. Both
exit non-zero. Read which one you got before reporting "nothing uses this".

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
- `--ticket=<id>` layers a named ticket instead of the one you are standing in,
  and **fails** if no such workspace exists rather than falling back to the
  fleet. That fallback would be the same mistake inverted — you asked for branch
  state and would have been handed main. If you get that error, check the id
  against `ls $TICKETS_ROOT` (the message lists what is there) instead of
  dropping the flag.

Always read the `searching:` line before trusting a layered answer. If it is
absent, no ticket was layered and every hit came from the fleet.

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

## The two questions that follow a search result

Both read manifests and CODEOWNERS rather than code, so both are `declared` —
the strongest kind for a negative, and the one most likely to be repeated to a
person as fact. Reach for them when a result raises "so who do I tell" or "is
everyone on the same version".

**`cs owns <repo>/<path>`** — who CODEOWNERS names, applying **last-match-wins**
as git does, and printing the rule that matched so you can judge whether it was
meant to cover that file:

```
inventory-api-dotnet/src/Infrastructure/SqlInventoryStore.cs	@acme/storage-team	.github/CODEOWNERS:4 [/src/Infrastructure/]
```

`cs owns` with no argument audits the fleet. A repo with **no** CODEOWNERS is
reported on stderr as a gap, not on stdout as an answer — "nobody owns it" is
not a conclusion this can reach. Never relay an owner as "the person who knows
this code": it is who is required to review, which is a different claim, and the
team named may no longer exist.

**`cs versions [coordinate]`** — which version each repo pins, flagged `AGREED`,
`DRIFT`, or `UNPINNED`. A shared contract library at two versions across a seam
is a real bug shape, and it is invisible to every search engine here because the
evidence is in manifests rather than in code:

```
acme-schemas	DRIFT	2 version(s)	external
  fulfillment-worker-python	==2.4.0	pyproject.toml
  web-monorepo-node	2.5.1	package.json
```

Versions are compared on the number, not the spelling, so `==2.4.0` and `2.4.0`
report as `AGREED` rather than as a false drift. It reads **manifests, not
lockfiles** — two repos agreeing here can still resolve differently at build
time, so report drift as a declaration mismatch, never as proof of what is
installed.

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
- **`cs def` reuses its index for 60 seconds.** The key is the commit each repo
  is on, so a fleet refresh or a branch change invalidates it — but *uncommitted*
  edits do not. The answer line says how old the index is; pass `--refresh` after
  editing a file you are about to look up. Measured 5.9s cold and 0.74s reused
  on a 456k-line fleet, which is why it is cached at all.
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
- **`cs uses` filters comments by file extension**, so its coverage is a table
  rather than a parser: 106 extensions plus 13 well-known filenames. A file in
  a language outside the table is passed through unfiltered and *named* in the
  answer line (`prose filtered except: .erl`). When you see that, the hits in
  those files are `cs seam` quality, not `cs uses` quality.
- **Some directories are never searched.** `node_modules`, `target`, `dist`,
  `vendor`, `bin`, `obj` and similar are excluded fleet-wide, and an excluded
  directory looks exactly like one with no hits. `cs engines` prints the
  effective list. Some layouts keep hand-written source in `bin` or real
  dependencies in `vendor` — if a file you know exists is not being found, check
  the list and rerun with `CS_EXCLUDE_REMOVE="bin vendor"`.

## Verifying it works

It ships a fixture fleet with known-correct answers, including decoys designed
to catch over-eager tools. `ROOT` below is `${CLAUDE_PLUGIN_ROOT:-.}`:

```sh
ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
"$ROOT/scripts/build-fixtures" /tmp/fixture-fleet
export FLEET_ROOT=/tmp/fixture-fleet
"$CS" uses "/api/v1/inventory/reserve" | "$ROOT/scripts/score-seams" reserve-consumers -
```

`score-seams --list` shows all nine queries. `fixtures/BASELINE.md` records how
each engine scores alone, and `fixtures/GROUND-TRUTH.md` explains what each
query is testing.

**Three layers:**

```sh
"$ROOT/scripts/verify-search"    # end-to-end: does the facade still answer all nine?
"$ROOT/scripts/verify-engines"   # per-engine: is each engine still doing its job?
"$ROOT/scripts/bench-scale"      # what it costs on a generated 456k-line fleet
```

`verify-engines` exists because **the facade hides engine regressions**:
`cs calls` falls back from ast-grep to semgrep, so ast-grep could break
entirely and the end-to-end run would still score 9/9. Each engine is therefore
probed directly on the one capability the routing depends on it for.

`verify-search` also has a **refusals** section, which tests that `cs` refuses
rather than that it answers. Those are different properties, and only the second
protects what this tool claims: a missing python3, a typo'd `--ticket`, or two
`cs def` calls issued in parallel all used to yield a confident empty answer
while every scored query still passed. If you are diagnosing a suspicious
negative result, run `verify-search` — it reproduces each of those directly.

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
checked. Say which it was, and say when a result was `PARTIAL`, capped,
`degraded`, or `prose filtered except:` — a confident summary of an incomplete
search is the failure this whole setup exists to prevent.

**Read stdout and stderr as different things.** stdout is the result stream and
nothing else — every hit, one per line, and never a diagnostic. Provenance,
warnings, the `searching:` line, the per-repo distribution of a capped result,
and the comment-only mentions excluded from a zero-hit `cs uses` all go to
stderr. If you pipe `cs` anywhere, you get results only; if you are judging how
much an answer is worth, you need the stderr side too.
