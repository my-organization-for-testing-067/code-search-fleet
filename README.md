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
scripts/verify-search              # 192 checks against a throwaway fixture fleet

scripts/cs which                   # which subcommand answers what
scripts/cs uses "/api/v1/orders"   # who uses this string, in code only
```

Every *engine* is optional; `cs engines` reports what is present and `cs` routes
around what is missing rather than failing silently.

**`python3` is the one hard requirement** — `uses`, `provides`, `deps`,
`publishes`, `versions`, `owns`, `impls`, `refs`, `fields` and symbol mode all
run through it. It is separate from the engines because it does not degrade:
those commands refuse rather than answer without it. Nothing installs it for you
(a system python is the OS's business), but `bootstrap` and `cs engines` both
report it.

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
| Where a type is constructed, all idioms | `cs constructs <Type> [repo]` |
| What implements this interface | `cs impls <symbol> <repo>` |
| What calls this symbol | `cs callers <symbol> <repo>` |
| What this symbol calls | `cs callees <symbol> <repo>` |
| What breaks if I change this symbol | `cs impact <symbol> <repo>` |
| Who reads or writes this field, fleet-wide | `cs fields <field> [repo]` |
| How big is that field's blast radius | `cs fields <field> --count` |
| What references this symbol (bridges DI) | `cs refs <symbol> <repo> <file>` |
| Which repo publishes this package | `cs provides <coordinate>` |
| Which repos depend on which | `cs deps [repo]` |
| Which version each repo pins, and where they disagree | `cs versions [coordinate]` |
| Who to ask about this repo or file | `cs owns [repo\|repo/path]` |
| When a seam appeared, or last changed | `cs history <string> [repo]` |
| What is actually being searched | `cs repos` |
| Which workspaces there are to search | `cs scopes` |
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
naming a workspace that is not there, or — for `cs impls` / `cs refs` — a repo
whose **language toolchain** is not installed. That last one was the tool's own
worst failure mode reproduced inside it: the preflight checked `uvx` and
`python3`, the *driver*, and said nothing about whether the language could be
analysed, so on a machine with no .NET SDK a C# repo produced

```
answer: resolved via serena (LSP) · 0 hit(s)
```

— the strongest negative in the taxonomy, asserted about a repo where nothing
had been read. `cs` now refuses, and never labels `resolved` an empty result the
language server did not affirmatively produce: an error, a timeout, or an empty
response refuse rather than answer.

`verify-search` has a whole section asserting each of these refuses, because none
of them failed a scored query — they were found by probing the failure paths,
not by reading the code.

### And a refusal is detectable, not merely explained

| Exit | Meaning |
|---|---|
| `0` | the query ran and found at least one hit |
| `1` | **refusal** — the query did not run, so nothing was ruled out |
| `2` | the query ran honestly and found nothing |

`1` and `2` are opposite facts and both used to be `1`, which left the tool's
central promise available only as prose on stderr. The obvious thing for a
caller to write —

```sh
if cs uses "$route" >/dev/null 2>&1; then echo "in use"; else echo "unused"; fi
```

— reported `unused` for a typo'd `FLEET_ROOT`. Asking the caller to read *which*
failure they got is a reasonable instruction for a human and a useless one for a
script.

A **broken** engine refuses as well, which is what makes `2` worth trusting.
`cs engines` can report what is on `PATH`; it cannot report that ripgrep is on
`PATH` and exiting 2 on every query, that the regex you typed does not compile,
or that `deps.py` is crashing. Each produced no output and was reported as
`0 hit(s)` — and splitting the exit codes made that *worse*, because a caller
correctly branching on `2` now gets "the answer is no" from a search that
crashed. Every engine's status is checked (`ripgrep`, `grep` and `ast-grep`
share the `0`/`1`/`≥2` convention; `semgrep` and `git` report `0` either way),
and an empty result from a failed engine refuses.

A file that could not be **read** is deliberately not in that category. ripgrep
uses exit 2 for "could not open one file out of 84,000" as well as for a broken
regex, and treating those alike meant a single committed symlink pointing at a
former colleague's home directory made *every zero-hit query on the fleet
refuse* — while queries with hits answered normally. `cs` parses the engine's
stderr, so a per-file error becomes `PARTIAL` with the skipped paths named, and
only a systemic failure refuses. Recursive `grep` skips such a file silently, so
`cs` finds it separately on that backend: a negative has to mean the same thing
whichever engine is installed.

### And the metadata is available as data

Everything that decides how much an answer is worth was prose on stderr — the
answer kind and the four warnings that must not be swallowed. `--porcelain` (or
`CS_JSON=1`) puts one JSON object on stdout instead of the result lines:

```json
{"cs":1,"subcommand":"uses","query":"…","scope":"PROJ-123",
 "view":"PROJ-123 (2 repo(s), your branch) + fleet (8 repo(s), main)",
 "exit":0,"refused":false,"kind":"heuristic","engine":"ripgrep","hits":2,
 "repos":2,"degraded":null,"partial":false,"truncated":false,"returned":2,
 "engine_errors":[],"results":[{"repo":"…","path":"…","line":7,"text":"…"}]}
```

Refusals carry the envelope too, with `refused: true` and the reason — the case
with no result stream to attach anything to. `hits` is how many exist and
`returned` how many came back, so a cap is visible without reading a warning.
stderr is untouched, so `--porcelain` composes with `--quiet`.

`scope` and `view` are the `searching:` line as data. A human running `cs` knows
which directory they are standing in; a caller reading the envelope chose
neither the directory nor the layering and could not otherwise tell which of
the two levels answered — so the provenance goes on stdout with everything else
that decides what the result is worth, and a caller that asked for a named
workspace can assert it got that workspace rather than `main`.

### And `cs engines` reports answer kinds, not just binaries

The contract is expressed in answer kinds; the install is a list of binaries;
nothing connected the two, so `ast-grep MISSING` / `semgrep MISSING` next to
five rows saying `ok` read as a healthy setup rather than as *the entire
`structural` tier is gone and `cs calls` will refuse*. `cs engines` now derives a
per-kind view from the same probes:

```
ANSWER KIND  STATUS
structural   UNAVAILABLE — needs ast-grep or semgrep, neither installed → cs calls and cs def both refuse
               backs: cs calls, cs def
resolved     DEGRADED — dotnet ok, java MISSING (Java/Kotlin), node ok → cs impls / cs refs refuse for the missing languages
               backs: cs impls, cs refs
textual      ok — ripgrep
               backs: cs text, cs seam
```

`degraded` is deliberately a third state: no ripgrep still yields `textual`
through the POSIX grep fallback, which is a slower route to the same kind, not a
missing kind. `cs why <kind>` reports the same availability alongside that
kind's blind spots.

### And where no language server can run, a graph answers instead

`cs impls` needs a language server, which needs its language's toolchain. For
.NET Framework C# that toolchain is Windows-only to build, so on macOS or Linux
the `resolved` tier is unavailable *by construction* — and refusing was `cs`'s
only answer there. When a repo has a tokensave graph, `cs impls` now falls back
to it:

```
! answered from a tokensave graph last synced 3 day(s) ago — it cannot see changes made since
! this is a GRAPH answer, not a language server: it cannot see reflection, DI
  registration, or generated code…
answer: structural via tokensave (graph) · 2 hit(s) · 1 repo(s)
```

Never labelled `resolved` — a graph is not a language server, and `cs refs`
remains the only thing here that bridges a DI registration. The query is
`implements` ∪ `extends`, because C# has one syntax for both relations (see
`fixtures/BASELINE.md`). `cs engines` reports graph age alongside the binaries,
since a graph is the one engine that can be confidently *wrong* rather than
merely blind.

`cs def` gets the same fallback: with no universal-ctags installed it reads the
graphs instead, and `--engine=tokensave` asks for them deliberately. The
trade-off is coverage — the ctags index spans the whole view in one pass, while
graphs are **per-repo** — so `cs` names the repos it could not cover:

```
! no tokensave graph, so NOT searched: pricing-lib-java web-monorepo-node …
  — a definition in those repos cannot be found this way
```

Without that line a definition living in an unindexed repo would look exactly
like a symbol that does not exist, which is the failure this whole project is
organised against.

### The field-level impact question, split by access kind

`cs uses` answers *"who is affected if I change field X"* textually, which is
the one shape text cannot express: it has no read/write distinction. That
matters because a field change has **two different blast radii**, and which one
you care about depends on the change:

- an **additive** change, or a changed **default**, can only be observed where
  the field is **written** — it is invisible anywhere the object is merely read
- a **removal, rename or retype** breaks where the field is **read**

A grep collapses both into one list, so reviewing a default-value change with a
text sweep returns precisely the sites where the change is *not* observable.

```
$ cs fields _threshold --fleet
fulfillment-worker-python/fulfillment/discounts.py:14: [write] in DiscountEngine::__init__ self._threshold = waiver_threshold_cents
fulfillment-worker-python/fulfillment/discounts.py:17: [read] in DiscountEngine::handling_fee_cents if subtotal_cents >= self._threshold:

write sites: 1 (shown 1) — these observe an added field or a changed default
read sites:  1 (shown 1) — these break on a removal, rename or retype
answer: structural via tokensave (graph) (2 repo graph(s), read/write split) · 2 hit(s) · 1 repo(s)
```

Unlike `cs callers` / `cs callees` / `cs impact`, this one is **fleet-wide**:
"who is affected" stops making sense at a repo boundary. Graphs are still
per-repo, so the union is assembled across them and the repos with no graph are
named — a field read in an unindexed repo looks exactly like a field nobody
reads.

Three things it refuses or discloses rather than guessing, all measured against
tokensave 7.9.0:

- **An empty answer refuses.** `field_sites` returns zero counts with exit 0 for
  a field that does not exist, in the identical shape it returns for a field
  that exists and is never touched — and `find_exact_symbol` reports count 0 for
  a *real* field too, because field nodes are not in that index. Nothing can
  separate the two, and *"nothing reads this field"* is the answer someone
  deletes a field on.
- **A `Type::field` qualifier that is not applied refuses.** The qualifier is
  parsed and then dropped, and the *bare-name* results come back regardless:
  `DiscountEngine::_threshold` and a fabricated `NoSuchClass::_threshold` return
  identical sites. Answering would put the broad question's result under the
  narrow question's heading.
- **At fleet scale, ask for counts instead.** A common field name overflows
  tokensave's 15000-character output on its *write* list alone, so the listing
  refuses — correctly, since a partial site list would understate the blast
  radius. `cs fields <field> --count` answers anyway, because the counts are
  emitted *before* the site arrays and survive the cut that destroys them:

  ```
  $ cs fields chargeAmount --fleet --count
  repo-a: writes 9, reads 41 (refs: 9 write, 63 read)
  repo-b: writes 3, reads 12

  total: writes 12, reads 53 site(s) across 2 repo(s) with a graph
  ```

  The headline numbers are **sites** — distinct `file:line`, the same quantity
  the listing reports, so the two modes agree. tokensave counts *occurrences*,
  which overstates a blast radius: three references on one line are one place a
  human edits, not three. The occurrence counts are kept alongside, and printed
  only where they differ. Where the output was truncated the arrays are
  incomplete, sites cannot be derived at all, and the row says it is counting
  references instead.

  These are the graph's own totals, not a returned-row count. That distinction
  is why this fans out per repo rather than querying the fleet-wide union graph:
  the union graph answers promptly but silently *caps* — its `write_count` came
  back as 20 with limit 20 and 21 with limit 21, so nothing separates "21 sites
  exist" from "21 of many were returned". An honest refusal beats a total nobody
  established.
- **The cap is per access kind, and engine truncation is `PARTIAL`.** Reads
  outnumber writes heavily, so one cap over the combined stream would spend the
  budget on reads and truncate the writes away. Separately, `tokensave tool`
  cuts its own stdout at 15000 characters — mid-token, leaving invalid JSON — so
  above roughly 75 sites the reads are re-requested with a limit and become a
  sample of an unknown total. That is reported as `PARTIAL` with the read count
  spelled `≥N`, never as a complete answer.

### A text answer says how much of itself is data

The size of a text answer is the first thing a reader takes from it, and a large
hit count reads as thorough coverage. Measured on a 43-repo fleet, `cs uses` on a
CamelCase type returned **1,295 hits** — of which 1,271 were data files and 1,192
came from a single test-resources CSV. The 24 source hits were the answer, and
under the 200-line cap almost none of them were shown.

Nothing was filtering wrongly: a CSV has no comment syntax, so there is nothing
to strip and every line legitimately passes. The defect was that the composition
was invisible — the answer did not distinguish 24-code-plus-1271-fixture from
1295-code, and `cs uses`'s own "in CODE" reads as a promise about file *kind*
when what it means is "with comments stripped where we know how".

Every text answer now reports its own composition, and warns when the data half
dominates:

```
$ cs uses OrderLineItem --fleet
...
! most of this answer is NOT source: composition: 24 in source, 1271 in
  data/doc files (.csv 1208, .json 19, .md 3) — --source-only excludes the data half
```

`--source-only` is the opt-in narrowing, and it is **not** the default: a route
in an `appsettings.json` is a real seam, and dropping it silently would be the
same class of error in the other direction. When used, it is declared in the
porcelain envelope's `exclusions`, not only on stderr.

The line is **data vs source, never test vs production**. A test file is often
the single most informative hit for an impact question — a test constructing a
request object *without* a field is exactly where a changed default becomes
observable — so test code always stays in scope. `.sql`, `.yaml` and `.xml` count
as source too: they have comment syntax, and a column named in a query is a real
use.

### And the same graph answers the symbol half of a question

`cs uses`, `cs seam` and `cs history` ask about **names**. `cs callers`,
`cs callees`, `cs impact`, `cs impls` and `cs fields` ask about **symbols**. Both are here
because a real question crosses between them — *"I am renaming this route, what
breaks"* starts as a seam question and ends as a symbol one — and the handoff to
a second tool with a second scoping model is the cost worth removing.

```
$ cs callers ReserveAsync inventory-api-dotnet
tokensave: 'ReserveAsync' is 2 nodes in this graph and ALL were asked
  (src/Infrastructure/SqlInventoryStore.cs:14, src/Domain/IInventoryStore.cs:5)
inventory-api-dotnet/src/Controllers/ReservationController.cs:27: [method] Reserve (calls)
answer: structural via tokensave (graph) (scoped to inventory-api-dotnet; fleet layer, synced 0d ago; direct callers) · 1 hit(s)
```

Three subcommands, not ninety. The tool behind this fronts dead code, coupling,
complexity, blame, test mapping, call chains and inheritance depth; wrapping all
of that would make `cs` a second, worse interface for something already good at
it and would cost the property that makes it legible — subcommands shaped like
questions, few enough to hold in your head. `cs which` points at the graph tool
directly for anything deeper, because a facade that quietly answers *less* than
the thing it fronts is worse than no facade.

What `cs` adds over calling the graph is the part the graph does not carry:

- **The answer kind.** `structural`, never `resolved`. A graph cannot see
  reflection, DI registration or generated code, and raw graph output says so
  nowhere.
- **Refusal discipline.** Two of the graph CLI's own tools take a node id and
  answer a bare *name* with an empty result and **exit 0**: `callers_for` returns
  `{"callers": {"<Name>": []}}` and `impact` returns `node_count: 0`, both having
  looked nothing up. "Nothing calls this" is the answer someone deletes code on,
  so every lookup is two-step — name → node id → question — and a name that does
  not resolve refuses instead of printing nothing. (`callers` and `callees`
  reject a bare name loudly, so only two of the four needed the guard; a name
  that is several nodes, like an interface method and its implementation, has
  all of them asked rather than the top-ranked one.)
- **The scope it actually had.** Below.

#### The layered view does not survive into symbol mode, and `cs` says so

`cs`'s best property is the layered view: ticket repos at branch state, every
other repo at main, one root. Graph indexes cannot do that. They are
per-project — the workspace copy of a repo has its own index, the fleet copy has
its own, and **there is no union**. So `cs callers <symbol>` cannot deliver what
`cs uses <string>` delivers, and left unsaid the gap is invisible in the output:
ask for callers of something you just renamed on your branch, get the fleet
index's answer, and it describes the world before your edit.

There is no clean fix, so the gap is made loud instead. Every symbol answer
names **which** index answered and how old it is, and an index from the wrong
layer is reported as `degraded` — which puts it in the porcelain envelope too,
where a non-human caller sees it without reading stderr:

```
$ cs callers ReserveAsync inventory-api-dotnet --ticket=PROJ-9
! the PROJ-9 workspace copy of inventory-api-dotnet has no graph, so its FLEET
  copy answered — this describes main, not your branch
answer: structural via tokensave (graph) (scoped to …; fleet layer, synced 0d ago; direct callers) · 1 hit(s)
! degraded: answered from inventory-api-dotnet's FLEET index (main) although the
  scope is PROJ-9 — graph indexes are per-project and there is no union of the
  two, so your branch's edits to inventory-api-dotnet are invisible in this answer
```

A caller who knows the answer excludes their branch can act on it; one who does
not, cannot. Build a graph in the workspace copy and the same query is answered
from it, with no warning to ignore — which is what keeps the warning worth
reading.

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
| `CS_JSON` | `1` for one JSON object on stdout instead of result lines (same as `--porcelain`) |
| `CS_CTAGS_BIN` | use exactly this universal-ctags; if it does not validate, ctags counts as absent |

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
looks exactly like a directory with no hits. And because that only helps if you
think to run it, any query with a non-default exclusion list now says so on the
answer:

```
! searching with a NON-DEFAULT exclusion list: +app (CS_EXCLUDE_EXTRA) — files
  under those directories were not searched, so this result may be narrower…
```

`EXTRA` gets the louder wording because it is the direction that manufactures
false negatives, and because these are environment variables: set one for a
single investigation and every later session is narrowed with no expiry.

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
`--fleet` is how you ask for the fleet on purpose, and `cs scopes` lists what
there is to choose between — which is what anything calling `cs` without a
working directory to stand in has to do first.

## Measuring what it actually did — opt-in, off by default

Two of this tool's claims are, in principle, falsifiable: that every answer is
labelled with **how** it was obtained, and that it **fails closed** rather than
reporting a broken engine's empty output as a clean negative. Neither is
measurable from the outside, and the second has a failure mode in the other
direction — a tool that refuses too often teaches its callers to route around
it. Two committed broken symlinks in one repo once made *every* zero-hit query
refuse, so for a stretch no negative result was obtainable at all; that was
caught only because someone happened to be evaluating at the time. As a refusal
rate it would have been a step change on a graph.

`CS_LOG` appends one JSON line per query recording the **outcome**:

```sh
export CS_LOG=1          # -> ~/.cache/cs-queries.jsonl; any other value is a path
```
```json
{"ts":"2026-08-17T12:00:00Z","v":"1.10.0","sub":"seam","query":"h:fa2c3cc2058d",
 "layer":"ticket+fleet","kind":"textual","engine":"ripgrep","outcome":"hits",
 "refusal":"none","hits":7,"repos":2,"ms":3512,"ms_res":"ms","partial":false,
 "warnings":["truncated"]}
```

`outcome` is `hits` / `zero` / `refused`, and a refusal carries a coarse
`refusal` class (`no-fleet-root`, `empty-fleet`, `no-python3`, `no-workspace`,
`engine-failed`, `bad-args`, `other`) — the refusal *messages* carry paths and
query strings and are deliberately not written down. Only the subcommands that
ask the code something are logged; `cs which`, `why`, `engines`, `scopes` and
`repos` cannot hit, miss or refuse, and counting them would dilute every rate
in the file.

**The query string is controlled separately from everything else.** Outcome,
kind, engine, hit count and latency are the analytically valuable fields and
none of them are sensitive; the query is the part that is proprietary in a
private fleet — internal route names, queue names, config keys, symbol names.

| `CS_LOG_QUERY` | writes | for |
|---|---|---|
| `hash` (default) | `"h:fa2c3cc2058d"` | repeat queries stay countable, the identifier is never on disk |
| `omit` | `null` | no query column at all |
| `plain` | the literal string | a fleet that wants it |

The hash is not a security boundary — a short internal identifier does not
survive a dictionary attack by anyone who already has the fleet. It exists so
that "this search ran 40 times this week" stays answerable without writing the
search down.

`ms_res` is `ms` or `s`, because the resolution is not the same everywhere:
`EPOCHREALTIME` needs bash 5 (macOS ships 3.2) and `date +%s%N` is GNU-only, so
the floor is the shell's whole-second counter. A latency graph built on
second-granularity data *without knowing that* is worse than no graph, so the
resolution is recorded next to the number rather than left to be inferred.

**JSONL rather than SQLite, deliberately.** The callers here are agent sessions
and several run at once, so the concurrent case is the normal one. One
`O_APPEND` write of one short line needs no locking, no schema migration, and
cannot be locked out under a fan-out of parallel queries; every field is
bounded so the line cannot grow to a size at which a single write may be split.
`verify-search` runs 16 real queries in parallel and requires 16 intact lines.
It also stays greppable, and anyone who wants SQL can load the JSONL.

The log is instrumentation, so it never costs the query anything: an unwritable
path warns on stderr and the search still answers. `cs engines` reports whether
the log is on and where — in both directions, since a log nobody knows is
running is the problem the opt-in default exists to avoid, and a log somebody
believes is running when it is not is how a measurement window turns out empty.
Rotation is left to you; it is an ordinary append-only file.

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
- Symbol mode is **per-repo, at one layer**. A graph index spans neither the
  fleet nor your ticket workspace, so `cs callers` finding nothing rules out
  callers in *that repo* and nothing else. Pair it with `cs uses` before calling
  anything dead.
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

### Updating

```sh
claude plugin marketplace update repo-fleet
claude plugin update code-search@repo-fleet
```

Both lines are load-bearing. The first refreshes the catalog so it knows a newer
version exists; running only the second updates against a stale catalog and
reports nothing to do. And the plugin **must** be named `code-search@repo-fleet`
— the bare `code-search` fails with `Plugin "code-search" not found`, which
reads like the plugin is not installed rather than like the id is incomplete.

Restart Claude Code afterwards; the CLI says so, and the previously loaded skill
stays in the session until you do.

### Running the scripts from a terminal

The whole repo ships with the plugin — the `cs` CLI, all five engines' glue, the
fixture fleet, and the verification suite — so `verify-search` runs from the
installed copy and answers "is this working *here*" rather than "did it work
where it was built".

`CLAUDE_PLUGIN_ROOT` is set **only inside a Claude Code session**, so the
`"$CLAUDE_PLUGIN_ROOT/scripts/…"` form used throughout `SKILL.md` expands to
`/scripts/…` in an ordinary shell and fails. Resolve the installed copy instead:

```sh
CS_ROOT=$(ls -d ~/.claude/plugins/cache/repo-fleet/code-search/*/ | tail -1)

"$CS_ROOT/scripts/bootstrap"        # install the engines (--check to only report)
"$CS_ROOT/scripts/verify-search"    # the full suite, against a throwaway fixture fleet
"$CS_ROOT/scripts/cs" which         # the decision table
```

`tail -1` picks the highest version, which matters because an update leaves the
previous version's directory in place. Substitute the marketplace you installed
from if it was not `repo-fleet`.

`verify-search` builds its own fixture repos, so it neither touches your code nor
needs `FLEET_ROOT` set — which makes it the right first thing to run, before the
fleet exists. It **ignores** an exported `FLEET_ROOT` rather than honouring it:
every check asserts fixture content, and the suite seeds probe files into the
fleet it runs against, so aiming it at a real one could only produce failures
that are not real while writing into repos it does not own. `--fleet <dir>`
overrides deliberately, and refuses a tree that is not a fixture fleet. The same
applies to `verify-engines`. Simply asking the agent to "verify code-search" also works, and
avoids the path entirely: the skill resolves it from `CLAUDE_PLUGIN_ROOT`.

**Cost: ~200 tokens always-on**, and the ~8.2k skill body only loads when a
search question actually comes up. `claude plugin details code-search` reports
both numbers for the version you actually have installed — prefer it to this
line, which is a snapshot: the always-on figure was ~150 before `cs owns` and
`cs versions` needed announcing in the description.

That split is the argument against exposing this over MCP *instead*: MCP tool
schemas sit in context for the whole session whether or not you search, so the
8.2k would be permanent rather than on demand.

It is not the argument against exposing it over MCP *as well* — see below.

From a plain clone instead, symlink the skill:

```sh
ln -s "$PWD/skills/code-search" ~/.claude/skills/code-search
```

Either way the skill resolves the CLI through `${CLAUDE_PLUGIN_ROOT}`, falling
back to the checkout — the working directory is the user's project, so `cs` is
never on a relative path.

### Also available over MCP, opt-in

The cost argument above — schemas are permanent, the skill body is on demand —
assumed a client that inlines every tool schema at session start. That is still
true of some, and there the objection stands unchanged. It is no longer true of
clients that **defer** tool schemas: tools arrive as names only, and a schema is
fetched when a tool is actually called. The standing cost there is a list of 21
identifiers — smaller than the always-on skill description it partly duplicates.

So `scripts/cs-mcp` exposes the same subcommands over MCP, and it is **opt-in**
rather than bundled with the plugin. A client that inlines schemas should not
be made to pay for a surface that is only cheap somewhere else:

```sh
# $CS_ROOT as resolved under "Running the scripts from a terminal" above
"$CS_ROOT/scripts/cs-mcp" --install     # prints the exact command, path resolved
"$CS_ROOT/scripts/cs-mcp" --self-check  # can it reach cs and your fleet from here?
"$CS_ROOT/scripts/cs-mcp" --tools       # the surface, without speaking the protocol
```

`--install` exists because the path is the whole difficulty: `CLAUDE_PLUGIN_ROOT`
is unset in the shell where you actually run `claude mcp add`, and an installed
plugin lives under a versioned cache directory nobody types from memory.

What it buys over the CLI is **reachability**, not capability. A tool an agent
must be told about is reached only when something remembers to tell it; a tool
in the tool list is reached because it is there. Prose that has to be loaded
first is the layer that fails. Measurement comes with it: usage rollups key on
the `mcp__<server>__` tool-name prefix, so calls are counted by name rather than
by matching the shape of a shell command — which undercounts precisely when
someone invokes it in a way the matcher does not recognise, and an uncounted
call is indistinguishable from non-use.

#### Every tool requires an explicit scope

This is the part that would otherwise break silently, so it is worth stating
plainly. `cs` resolves the ticket workspace from `$PWD`. That is right for a
CLI — you are standing in the workspace — and **meaningless for a server**,
which is a long-lived process whose working directory is wherever the client
launched it and which does not move when you do.

A server that inherited that cwd would make every MCP query a silent fleet-only
search: stale copies of the files you are editing, answered from `main`, with
none of the `searching:` provenance that makes the substitution visible. That
is the worst failure available here — a confident wrong answer arriving through
a new door.

So `scope` is a **required** argument on every tool that reads the fleet, with
no default and no detection. `cs_scopes` lists the valid values, `"fleet"` is
spelled out as one of them so that searching `main` alone is a choice rather
than a fallback, and every result carries the same provenance line the CLI
prints:

```
searching: PROJ-123 (2 repo(s), your branch) + fleet (8 repo(s), main)
answer: heuristic via ripgrep (literal, prose filtered) · 2 hit(s) · 2 repo(s)
```

The refusal/zero-hit distinction survives the crossing too: a query that ran
and found nothing comes back as a normal result saying so, and a query that did
not run comes back with `isError` — the same two facts the exit codes carry,
which would otherwise collapse into one at the boundary.

`verify-search` covers all of this, including a differential that issues the
same request from two working directories and requires the answers to match.

## License

[Apache-2.0](LICENSE). Chosen over MIT for the explicit patent grant, which is
what makes a corporate legal review a formality rather than a conversation —
this is tooling meant to be installed on work machines and pointed at a
company's source, so "may we use this" needs an answer that is already written
down. Without a LICENSE file the default is all rights reserved, which blocks
not just use but vendoring, internal mirroring, and redistribution through an
internal plugin marketplace.
