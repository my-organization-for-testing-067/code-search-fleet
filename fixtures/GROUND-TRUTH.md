# Fixture ground truth

Every deliberate relation planted in `fixtures/repos/`. Use this to check what a
search tool actually finds. Seams 1–5 cross repo boundaries; seam 6 is in-repo
and is the one both grep and static graphs are expected to miss.

## 1. REST route — .NET ← Kotlin

`/api/v1/inventory/reserve`

- Served by `inventory-api-dotnet/src/Controllers/ReservationController.cs`
  (`[Route("api/v1/inventory")]` + `[HttpPost("reserve")]` — note the path is
  **split across two attributes**, so a literal search for the full path finds
  only the caller).
- Called from `checkout-service-kotlin/.../InventoryClient.kt` (`RESERVE_PATH`).

A correct answer names both files and notes the split-attribute construction.

## 2. Kafka topic — Kotlin → Python

`orders.reserved.v1`

- Produced in `checkout-service-kotlin/.../EventPublisher.kt` (`ORDERS_RESERVED_TOPIC`).
- Consumed in `fulfillment-worker-python/fulfillment/consumer.py` (`ORDERS_RESERVED_TOPIC`).

Both sides use the same literal, so plain grep should get this one.

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
