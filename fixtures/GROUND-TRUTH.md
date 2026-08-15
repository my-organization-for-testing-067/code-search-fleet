# Fixture ground truth

Every deliberate relation planted in `fixtures/repos/`, plus the **decoys** —
things engineered to look like a relation but which are not. Seams 1–5 cross
repo boundaries; seam 6 is in-repo and is the one both grep and static graphs
are expected to miss.

The decoys are the part that measures accuracy. Positive cases alone only
measure recall, and are trivially gamed: a tool that reports everything as
related scores perfectly. Every decoy below is a plausible production
situation, not a synthetic trick.

`expectations.json` is the machine-readable form of this file; score an
answer against it with `scripts/score-seams`. Naive-grep results are in
`BASELINE.md`.

## Decoys at a glance

| Decoy | Where | Mistake it catches |
|---|---|---|
| Prose mention of the reserve path | `fulfillment-worker-python/fulfillment/consumer.py` docstring | Counting text matches as call sites |
| Second consumer of the reserve endpoint | `web-monorepo-node/packages/admin-ui/src/restockTool.ts` | Stopping at the first caller found (recall failure) |
| Dead `release` endpoint | `inventory-api-dotnet/.../ReservationController.cs` | Inventing a consumer for unused code |
| `orders.reserved.v2` consumer with no producer | `web-monorepo-node/packages/analytics/src/eventStream.ts` | Version-blind topic matching |
| Unrelated `DiscountEngine` | `fulfillment-worker-python/fulfillment/discounts.py` | Conflating same-named symbols across repos |
| `inventory.reserve.enabled.legacy` | `web-monorepo-node/.../FeatureToggles.ts` | Substring matching on config keys |

## 1. REST route — .NET ← Kotlin

`/api/v1/inventory/reserve`

- Served by `inventory-api-dotnet/src/Controllers/ReservationController.cs`
  (`[Route("api/v1/inventory")]` + `[HttpPost("reserve")]` — note the path is
  **split across two attributes**, so a literal search for the full path finds
  only the callers, never the definition).
- Called from `checkout-service-kotlin/.../InventoryClient.kt` (`RESERVE_PATH`).
- Called **also** from `web-monorepo-node/packages/admin-ui/src/restockTool.ts`
  (`RESERVE_ENDPOINT`). Two consumers, not one.
- **Not** called from `fulfillment-worker-python/fulfillment/consumer.py`,
  whose module docstring mentions the path in prose only.

A correct answer names the definition and both consumers, excludes the
docstring, and notes the split-attribute construction.

Same repo, `[HttpPost("release")]` — `/api/v1/inventory/release` — has **no
consumers anywhere in the fleet**. The correct answer to "who calls release?"
is "nobody, it is dead."

## 2. Kafka topic — Kotlin → Python

`orders.reserved.v1`

- Produced in `checkout-service-kotlin/.../EventPublisher.kt` (`ORDERS_RESERVED_TOPIC`).
- Consumed in `fulfillment-worker-python/fulfillment/consumer.py` (`ORDERS_RESERVED_TOPIC`).

Both sides use the same literal, so plain grep gets the pair — but it also
drags in the decoy below unless the version suffix is respected.

**Decoy:** `web-monorepo-node/packages/analytics/src/eventStream.ts` subscribes
to `orders.reserved.v2`, which **nothing produces**. Linking it to the Kotlin
publisher invents a relationship. Separately, "which consumer has no producer?"
is a legitimate question whose correct answer is exactly this file — an
orphaned consumer left behind by a version bump, which is a real bug shape.

## 3. Proto contract — Python ↔ Node

`ReservationEvent` (fields `orderId`, `sku`, `reservationId`)

- `fulfillment-worker-python/fulfillment/contracts.py` — hand-written mirror,
  snake_case attributes, camelCase JSON keys.
- `web-monorepo-node/packages/schemas/src/reservation.ts` — generated interface.
- Also constructed inline as a JSON string literal in
  `checkout-service-kotlin/.../EventPublisher.kt`, which is a third definition
  of the same shape and the likeliest place for drift.

A correct answer finds all three, including the Kotlin string literal.

## 4. Feature flag key — .NET ↔ Node

`inventory.reserve.enabled`

- Read in `inventory-api-dotnet/src/Controllers/ReservationController.cs`.
- Declared in `web-monorepo-node/packages/admin-ui/src/FeatureToggles.ts`
  as `FLAG_INVENTORY_RESERVE`, toggled by `disableReservations()`.

## 5. Shared package version — Python ↔ Node

`acme-schemas==2.4.0` / `"acme-schemas": "2.4.0"`

- `fulfillment-worker-python/pyproject.toml`
- `web-monorepo-node/package.json`

Plus `com.acme:pricing-lib:1.8.2` in `checkout-service-kotlin/build.gradle.kts`,
which is the `pricing-lib-java` repo.

**Decoy:** `fulfillment-worker-python/fulfillment/discounts.py` defines its own
`DiscountEngine`, unrelated to `com.acme.pricing.DiscountEngine` — same name,
different purpose, never reaches checkout. Any tool matching on symbol name
alone will merge them.

**Decoy:** `FeatureToggles.ts` also declares `inventory.reserve.enabled.legacy`,
a retired flag whose key is a superstring of the live one in seam 4. Substring
matching reports it as the same flag.

## 6. DI indirection (in-repo, expected to be missed)

In `inventory-api-dotnet`, `ReservationController` depends on `IInventoryStore`.
The only implementation, `SqlInventoryStore`, is named nowhere except the
`AddScoped<IInventoryStore, SqlInventoryStore>()` registration in `Program.cs`.

"What runs when `Reserve` is called?" requires: controller → interface →
DI registration → implementation → `IStockLedger` → its registration. Neither
grep nor a tree-sitter call graph bridges the registration step. Watch whether a
tool claims a complete call graph here — that is the honest failure case, and any
tool that reports full confidence is overselling.

## Language coverage

One repo per stack in use: C# (`inventory-api-dotnet`), Kotlin
(`checkout-service-kotlin`), Python (`fulfillment-worker-python`), TypeScript
monorepo (`web-monorepo-node`), Java (`pricing-lib-java`).
