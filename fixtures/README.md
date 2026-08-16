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

The exception is accuracy. The fixture carries **decoys** — a prose-only
mention of an endpoint, a consumer of a topic version nobody produces, a
same-named but unrelated class, a dead endpoint, a retired flag key that is a
superstring of a live one — so a tool cannot score well by being over-eager.
Those cases transfer to real repos even though the code around them does not,
because they are about how a tool decides two things are related, not about
scale.

Seam 6 is the other honest case: a DI indirection no static tool can resolve,
there to catch a tool overselling call-graph completeness.

## Scoring

`expectations.json` holds machine-readable expected/forbidden file sets.

```sh
scripts/score-seams --list                              # the nine queries
rg -n "orders\.reserved" | scripts/score-seams orders-reserved-v1 -
```

`BASELINE.md` records how naive grep scores, as the floor an indexed tool must
beat. Note its stated limitation: the scorer checks which files an answer
names, not whether the reasoning was sound, so some passes are hollow. Failures
are the trustworthy signal.

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

## Running one of them

`docker-compose.yml` brings up **inventory-api** so the HTTP boundary between it
and checkout can be exercised instead of read:

```sh
docker compose -f fixtures/docker-compose.yml up -d --build
curl -X POST http://localhost:18080/api/v1/inventory/reserve \
  -H 'content-type: application/json' -d '{"sku":"SKU-1","quantity":1}'
```

The response comes back **indented**, which is the whole point — that is the
serializer setting the PROJ-388 incident turns on, and the shape a hand-written
test payload in another repo will not have. ai-toolbox's `scripts/verify-contract`
drives checkout's real `InventoryClient` against this and checks that the
PROJ-388 introducing commit fails against it.

Port 18080 rather than 8080, so it does not fight with whatever is already
running; override with `INVENTORY_PORT`. Only this one service is here — a
broker for the `orders.reserved.v1` side is a separate increment.
