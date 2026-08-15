# Naive-grep baseline

Run 2026-08-15 against the fixture fleet, scoring a single `rg` invocation per
query with `scripts/score-seams`. This is the floor any indexed tool has to
beat. Reproduce with the commands in each row.

**5 of 9 pass — but 3 of those passes are hollow (see below), so the honest
score is closer to 2/9.**

| Query | Result | Why |
|---|---|---|
| `reserve-consumers` | FAIL | Both real callers found, but the Python docstring that merely *mentions* the path counts as a third caller. |
| `reserve-definition` | FAIL | Missed entirely. The .NET side assembles the path from `[Route("api/v1/inventory")]` + `[HttpPost("reserve")]`, so the full literal exists nowhere in that repo. |
| `release-consumers` | PASS | Correctly returns nothing for the dead endpoint. |
| `orders-reserved-v1` | FAIL | Pulls in the analytics consumer, which subscribes to `orders.reserved.v2` — a relationship that does not exist. |
| `orphaned-consumer` | PASS\* | Names the right file, but only because the grep output happens to contain it. |
| `reservation-event-shape` | PASS\* | Found the Kotlin file via a *comment* containing "ReservationEvent", not via the inline JSON literal that is the actual third definition. |
| `reserve-flag` | PASS | Both sides found; the `.legacy` superstring did not mislead. |
| `discount-engine` | FAIL | Conflates the unrelated Python `DiscountEngine` with the Java one checkout actually uses. |
| `reserve-implementation` | PASS\* | Names all three files by symbol match without bridging the DI registration at all. |

## What the hollow passes reveal about the scorer

`score-seams` checks **which files an answer names**, not whether the tool
understood the relationship. Three queries pass on that basis while getting the
reasoning wrong or skipping it:

- `reservation-event-shape` — right file, wrong reason (comment, not code).
- `reserve-implementation` — right files, no DI bridging. A tool that lists
  these three files and *claims a complete call graph* is wrong in a way this
  scorer cannot see.
- `orphaned-consumer` — the question needs produced-vs-consumed topic sets
  compared across repos; grep just dumps both and leaves the reasoning to the
  reader.

So treat the score as necessary, not sufficient. For those three, read the
answer's reasoning too. The failures are trustworthy in a way the passes are
not: a FAIL means the tool definitely got something wrong.

## Not yet run

Nothing has been measured against tokensave or any other index — it is not
installed. The comparison this baseline exists for is still outstanding.
