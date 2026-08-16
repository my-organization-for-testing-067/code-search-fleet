# code-search-fleet

One search interface over many repositories, backed by whichever engine can
actually answer the question.

Across nine scored queries with known-correct answers, the best individual
engine gets **5/9**. This gets **9/9** — not by being cleverer, but by routing
each question to the engine suited to it and doing the few things none of them
do alone.

## Why

No single search engine answers every question about a codebase:

- **ripgrep** cannot see a route assembled from two C# attributes, and counts a
  docstring mentioning an endpoint as a caller.
- **A symbol graph** cannot see a string literal in argument position — which
  is what cross-repo seams are made of.
- **An LSP** resolves an interface to its implementation, but needs a working
  toolchain per language and minutes to index.
- **None of them** read build manifests, so none can tell you which of two
  same-named classes another repo actually depends on.

Committing to one engine means accepting its blind spot permanently.

## Quick start

```sh
scripts/bootstrap                  # install engines (--check to only report)
export FLEET_ROOT=~/code/fleet     # a directory holding your repos
scripts/verify-search              # 34 checks against a throwaway fixture fleet

scripts/cs which                   # which subcommand answers what
scripts/cs uses "/api/v1/orders"   # who uses this string, in code only
```

Every *engine* is optional; `cs engines` reports what is present and `cs` routes
around what is missing rather than failing silently.

**`python3` is the one hard requirement** — `uses`, `provides`, `deps`,
`publishes`, `impls` and `refs` all run through it. It is separate from the
engines because it does not degrade: those commands refuse rather than answer
without it. Nothing installs it for you (a system python is the OS's business),
but `bootstrap` and `cs engines` both report it.

`timeout(1)` is worth having too. Without it a hung language server hangs `cs`
with no upper bound, and a search that never returns is the one outcome worse
than a wrong one, because nothing reports it. `brew install coreutils` on macOS.

## Commands

| Question | Command |
|---|---|
| Who calls/uses this endpoint, topic, config key | `cs uses <string>` |
| Which repos share this string | `cs seam <string>` |
| Any text or regex, comments included | `cs text <pattern>` |
| Where is a symbol defined | `cs def <symbol> [repo]` |
| Calls shaped like X, or taking literal Y | `cs calls '<pattern>' [lang]` |
| What implements this interface | `cs impls <symbol> <repo>` |
| What references this symbol (bridges DI) | `cs refs <symbol> <repo> <file>` |
| Which repo publishes this package | `cs provides <coordinate>` |
| Which repos depend on which | `cs deps [repo]` |
| Which version each repo pins, and where they disagree | `cs versions [coordinate]` |
| Who to ask about this repo or file | `cs owns [repo\|repo/path]` |
| When a seam appeared, or last changed | `cs history <string> [repo]` |
| What is actually being searched | `cs repos` |
| How much to trust an answer | `cs why [kind]` |

## Every answer says what kind of answer it is

A perfect score on a fixture is not the goal; some questions are undecidable
statically at any budget. So each result is labelled with the evidence behind
it — `resolved`, `declared`, `historical`, `structural`, `heuristic`, or
`textual`:

```
answer: heuristic via ripgrep (literal, prose filtered) · 2 hit(s) · 2 repo(s)
  --why for what a heuristic answer cannot see
```

This matters most for **negative** results, which is where a search tool does
real damage: "nothing uses this" from a `textual` match is close to worthless
evidence, while the same answer from `cs refs` is strong. `cs why <kind>` prints
what that kind cannot see.

`cs` is also loud about the four ways a result can be less than it looks: an
engine that hit its timeout says `PARTIAL` rather than returning empty, a capped
result says `showing N of M` and prints the per-repo distribution, a fallback to
a different engine says `degraded:`, and a `cs uses` that met a language its
prose filter does not know names it rather than claiming a filter that did not
run:

```
answer: heuristic via ripgrep (literal, prose filtered except: .erl) · 6 hit(s)
```

### And it refuses rather than answering empty

The worst thing this tool can produce is not a wrong answer but a confident
*negative* — a well-formatted, correctly-labelled, entirely empty result caused
by a malfunction rather than by an absence. "No code uses this" is what makes
deleting a live endpoint look safe.

So the conditions that would manufacture one are fatal, not silent: a fleet root
that does not exist or holds no repos, a missing `python3`, a `--ticket=<id>`
naming a workspace that is not there. `verify-search` has a whole section
asserting each of these refuses, because none of them failed a scored query —
they were found by probing the failure paths, not by reading the code.

## Tuning it for your repos

| Variable | Does |
|---|---|
| `FLEET_ROOT` | the directory holding your repos — **required**, no useful default |
| `TICKETS_ROOT` | where per-ticket workspaces live |
| `CS_MAX_RESULTS` | result cap, default 200 (`0` or `--all` for none) |
| `CS_TIMEOUT` | per-engine wall-clock limit in seconds, default 120 |
| `CS_TAGS_TTL` | how long `cs def` reuses its symbol index, default 60s |
| `CS_TEXT_ENGINE` | force `rg` or `grep`, so the two can be compared rather than trusted |
| `CS_EXCLUDE_EXTRA` | directories to skip, added to the built-in list |
| `CS_EXCLUDE_REMOVE` | directories to **stop** skipping |

`CS_EXCLUDE_REMOVE` matters more than it looks. The built-in exclusion list is a
guess about other people's repos, and some entries are wrong for some of them:
`bin` and `build` are generated in most layouts and hand-written source in
others, and a Go fleet keeps real dependencies in `vendor`. An excluded
directory produces a silent false negative — the hit simply is not there — so
removing an entry has to be as easy as adding one:

```sh
CS_EXCLUDE_REMOVE="bin vendor" cs uses "/api/v1/orders"
```

`cs engines` prints the effective list, because a directory excluded by mistake
looks exactly like a directory with no hits.

## Two levels

Built for a **fleet** directory of repos on main plus per-ticket **workspaces**
containing worktrees of only the repos being changed. Run `cs` inside a ticket
workspace and it layers that ticket's branch state over the rest of the fleet:

```
searching: PROJ-123 (2 repo(s), your branch) + fleet (8 repo(s), main)
```

Searching only the ticket would miss callers in repos the ticket does not
contain — the failure that makes renaming a shared route look safe.

`--ticket=<id>` searches a named workspace instead of the one you are standing
in, and **fails** if that workspace does not exist. Falling back to the fleet
would be the same mistake inverted: you asked for your branch state and would
have been handed main, with no `searching:` line to reveal the substitution.
`--fleet` is how you ask for the fleet on purpose.

## Verifying

```sh
scripts/verify-search      # end-to-end: does the facade still answer everything?
scripts/verify-engines     # per-engine: is each engine still doing its job?
scripts/bench-scale        # what it costs on a generated 456k-line fleet
```

Both matter. `verify-search` alone is not enough because **the facade hides
engine regressions**: `cs calls` falls back from ast-grep to semgrep, so
ast-grep could break entirely and the end-to-end run would still pass. (The
fallback now announces itself, but a passing score still would not.)

`verify-search` also asserts that **the two text backends agree**. Ripgrep
defaults to skipping dotted paths and honouring `.gitignore` while POSIX grep
does neither, so before those flags were pinned a config key in `.github/` was
found on a machine without ripgrep and missed on one with it. An answer that
depends on which engine happens to be installed is worse than a slow one,
because nothing tells you which answer you got.

`verify-engines` also probes **known limitations**, not just capabilities, and
reports `IMPROVED` when one disappears — an upgrade can remove the reason a
tool was rejected, and nothing else would notice.

And `verify-search` tests that `cs` **refuses**, not only that it answers. Those
are different properties, and only the second protects the claim the tool makes.
Every check in that section reproduces a defect that passed all nine scored
queries: a missing `python3` reporting zero hits, six concurrent `cs def` runs
racing on one index file and half returning nothing, a typo'd `--ticket`
answering from main, a language the prose filter could not parse being reported
as filtered anyway.

Two of those are worth naming as a lesson about the tests themselves. A check
that quietly downgrades is worse than no check: piping a long-running producer
into `grep -q` under `set -o pipefail` reports failure by SIGPIPE, so merely
*appending a line* to `cs engines` output turned the timeout-visibility check
into a `SKIP` while the run still said `0 failed`. And a check with no positive
control passes for the wrong reason — asserting only that a comment token is
absent succeeds just as well when the command is broken and finds nothing at
all, which is why every language probe now asserts both halves.

## The fixture

`fixtures/` holds five small repos (C#, Kotlin, Python, TypeScript, Java) with
deliberately planted cross-repo seams **and decoys**: a prose-only mention of an
endpoint, a consumer subscribed to a topic version nobody produces, a
same-named class in an unrelated repo, a dead endpoint, a retired config key
that is a superstring of a live one.

The decoys are the point. Positive cases alone measure recall and are trivially
gamed — a tool answering "everything is related to everything" scores perfectly.
`fixtures/GROUND-TRUTH.md` explains each; `fixtures/BASELINE.md` records how
every engine scores alone.

`fixtures/prose-probes/` is a second, deliberately unglamorous fixture: one file
per language, each carrying one token that appears only in comments and one that
appears only in code. It exists because the five repos above share a blind spot —
they are written in languages the prose filter supported from the start, so a
filter that silently did nothing for C++, Go, Ruby or PHP passed every query.
Twelve languages are covered; adding one is dropping in a `probe.<ext>`.

They also **build and test for real**, each with a GitHub Actions workflow:
`dotnet test`, `gradle test`, `pytest`, and a TypeScript typecheck. That makes
the declared dependency edge executable rather than decorative — Gradle
substitutes `com.acme:pricing-lib` for the sibling `pricing-lib-java` checkout,
so the edge `cs deps` reports is the edge the build actually resolves. It also
gives anything layering incidents on top a real defense layer to inspect.

## Layering in your own incidents

The fixture repos here exist to test search. If you are testing a *workflow* on
top of them — a postmortem process, a review checklist — seed the defects in
your own repo and layer them in:

```sh
scripts/build-fixtures /tmp/fleet --incidents-dir ~/my-toolbox/fixtures/incidents
```

Each incident directory supplies `incident.env`, `before/`, and commit messages;
`build-fixtures` regresses the touched files, commits that as the introducing
change, adds unrelated commits, then restores them as the fix — and asserts the
replayed tip matches the canonical tree, so history cannot drift from source.

## Honest limits

- Cross-repo, **cross-language** relations are strings. `cs uses` finds them;
  nothing resolves them symbolically. Report such links as textual matches.
- Runtime indirection — DI resolved from config, reflection, identifiers built
  at runtime — is undecidable statically at any budget.
- 9/9 on this fixture means the test set is exhausted, not that search is
  solved. The real measure is a query set drawn from your own tickets.
- Result caps and timeouts mean an answer can be partial. `cs` says so when it
  is, which is the mitigation — not a guarantee that it is not.

## Use with an AI agent

`skills/code-search/SKILL.md` is a self-contained entry point — setup, routing,
blind spots, verification.

### As a Claude Code plugin

This repo is its own marketplace:

```sh
claude plugin marketplace add my-organization-for-testing-067/code-search-fleet
claude plugin install code-search@code-search-fleet
```

Or get it together with the workspace tooling it is designed to sit beside, from
one catalog — see
[repo-fleet](https://github.com/my-organization-for-testing-067/repo-fleet),
which owns the fleet and ticket-workspace side and lists this plugin too:

```sh
claude plugin marketplace add my-organization-for-testing-067/repo-fleet
claude plugin install code-search@repo-fleet
claude plugin install fleet-workspace@repo-fleet
```

Then set the one thing it cannot guess:

```sh
export FLEET_ROOT=~/code/fleet     # the directory holding your repos
```

The whole repo ships with the plugin — the `cs` CLI, all five engines' glue, the
fixture fleet, and the verification suite — so `verify-search` runs from the
installed copy and answers "is this working *here*" rather than "did it work
where it was built".

**Cost: ~150 tokens always-on**, and the skill body only loads when a search
question actually comes up (`claude plugin details code-search` reports it).
That is the argument against exposing this over MCP instead: MCP tool schemas
sit in context for the whole session whether or not you search.

From a plain clone instead, symlink the skill:

```sh
ln -s "$PWD/skills/code-search" ~/.claude/skills/code-search
```

Either way the skill resolves the CLI through `${CLAUDE_PLUGIN_ROOT}`, falling
back to the checkout — the working directory is the user's project, so `cs` is
never on a relative path.
