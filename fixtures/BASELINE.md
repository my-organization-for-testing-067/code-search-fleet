# Baseline: naive grep vs tokensave

Run 2026-08-15 against the fixture fleet, scoring one query per tool per
question with `scripts/score-seams`. tokensave 7.9.0, installed via Homebrew;
all five fixture repos indexed with `tokensave init` (4–5 files each, 12–29ms).

**Headline: grep 5/9, tokensave 4/9 — and they fail on different questions.**
Neither is close to sufficient alone. Three of grep's passes are hollow (right
file, wrong or absent reasoning), so the honest read is that tokensave wins two
questions cleanly, grep wins one cleanly, and both fail three.

| # | Query | grep | tokensave | Notes |
|---|---|---|---|---|
| 1 | `reserve-consumers` | FAIL | FAIL | Both find the two real callers and both add the Python docstring as a third. Different mechanisms: grep matched prose text, tokensave matched symbol names in the same file. |
| 2 | `reserve-definition` | FAIL | **PASS** | tokensave's win. It surfaces the `Reserve` method with signature `[HttpPost("reserve")]`; grep can't, because the full path is assembled from two attributes and exists nowhere as a literal. |
| 3 | `release-consumers` | PASS | PASS | Both correctly report the dead endpoint has no consumers. |
| 4 | `orders-reserved-v1` | FAIL | **PASS** | tokensave's win. Matching the symbol `ORDERS_RESERVED_TOPIC` naturally excludes the v2 analytics consumer; grep's string match drags it in. |
| 5 | `orphaned-consumer` | PASS\* | PASS\* | Both name the file; neither actually compares produced against consumed topic sets. |
| 6 | `reservation-event-shape` | PASS\* | FAIL | tokensave misses the inline JSON literal in Kotlin — it isn't a symbol. grep's "pass" came from a *comment* containing the word, not the literal either. |
| 7 | `discount-engine` | FAIL | FAIL | Both conflate the unrelated Python `DiscountEngine` with the Java one. Name-based matching fails identically in both. |
| 8 | `reserve-flag` | **PASS** | FAIL | grep's win. tokensave misses `_flags.IsEnabled("inventory.reserve.enabled")` in C# entirely, because the key is a bare string literal, not a symbol. |
| 9 | `reserve-implementation` | PASS\* | FAIL | tokensave finds `SqlInventoryStore` but not the controller or the DI registration. grep's "pass" was naming three files by symbol match without bridging DI at all. |

\* Hollow pass: `score-seams` checks which files an answer names, not whether
the reasoning was sound. A FAIL is trustworthy; a PASS still needs reading.

## The two findings that should drive the decision

**1. String literals are not symbols.** tokensave indexes a symbol graph, so
route paths, topic names, and config keys are invisible to it unless they
happen to be bound to a named constant. Query 8 is the clean demonstration:
the .NET side passes the flag key as a bare argument and tokensave cannot see
it. This matters because cross-repo seams *are* strings — which is precisely
the "global relations across repos" use case. A symbol graph does not replace
grep for that; it cannot.

**2. `implements` edges exist only for Java.** Ranking the graph by that edge
kind across the fleet:

| repo | language | `implements` edges |
|---|---|---|
| pricing-lib-java | Java | 1 (correct) |
| inventory-api-dotnet | C# | **0** |
| checkout-service-kotlin | Kotlin | **0** |
| fulfillment-worker-python | Python | **0** |
| web-monorepo-node | TypeScript | **0** |

`SqlInventoryStore : IInventoryStore` is not in the C# graph, and
`implementations --trait IInventoryStore` returns zero matches. Interface to
implementation is the single most valuable relation in a DI-heavy .NET
codebase, and for four of the five languages here it is simply absent. All five
are in tokensave's "lite" tier, its best-supported one. Note also that the
installed binary reports 34 languages, not the 50+ the README advertises.

## Token cost

Bytes of raw tool output for the same question:

| Query | ripgrep | tokensave |
|---|---|---|
| Q2 (find definition) | 389 | 2,858 |
| Q9 (trace implementation) | 936 | 1,311 |

tokensave's own savings counter read `0` after this run. **On this fixture it
costs more tokens than grep, not fewer** — its JSON carries signatures and
method bodies.

Read that with care in both directions: the fixture is five files per repo,
where grep output is trivially small anyway. The savings argument is about
avoiding *file reads* while an agent explores a large codebase, and that cannot
be validated or refuted at this scale. What this does show is that the raw
output is verbose, and verbosity does not shrink on bigger repos.

## Still unmeasured

The question this baseline was built to inform — does indexing pay for itself
on a 100K+ LOC repo with real queries — needs a real repo and a query set from
real tickets. Nothing here substitutes for that.
