# Fixture repos

Five tiny repos — one per stack in use (C#, Kotlin, Python, TypeScript, Java) —
with deliberately planted cross-repo seams.

**What these are for:** testing that the *mechanics* work. Does `new-ticket`
create usable worktrees? Does `tokensave branch add` inherit the fleet index
instead of building one cold? Does `refresh-fleet` leave worktrees intact? Does
cross-repo graph querying resolve? Being tiny is correct for those questions.

**What these are not for:** judging whether a search tool is good. This code is
clean, small, and its seams were planted on purpose — every tool will score well
on it. That question needs real queries against a real repo; see the
"Evaluating the tooling" section of `docs/repo-fleet.md`.

The one exception is seam 6 in `GROUND-TRUTH.md`, a DI indirection that static
tools genuinely cannot resolve. It is there so a tool overselling its call-graph
completeness is caught.

## Usage

```sh
scripts/build-fixtures /tmp/fixture-fleet
export FLEET_ROOT=/tmp/fixture-fleet
export TICKETS_ROOT=/tmp/fixture-tickets
```

Each fixture is built as a bare origin plus a working clone, so fetch, reset,
worktree, and branch operations behave like real repos.

`GROUND-TRUTH.md` lists every planted relation and what a correct answer looks
like. Read it *after* running a search, not before.
