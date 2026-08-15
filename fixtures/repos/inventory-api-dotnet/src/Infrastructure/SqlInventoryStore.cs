using Acme.Inventory.Domain;

namespace Acme.Inventory.Infrastructure;

// Reached only through IInventoryStore, wired up in Program.cs. Nothing in the
// codebase names this type at a call site -- the DI blind spot the fixture is
// meant to exercise.
public class SqlInventoryStore : IInventoryStore
{
    private readonly IStockLedger _ledger;

    public SqlInventoryStore(IStockLedger ledger) => _ledger = ledger;

    public async Task<ReservationResult> ReserveAsync(string sku, int quantity)
    {
        var available = await _ledger.CountAsync(sku);
        if (available < quantity)
        {
            return new ReservationResult(false, "insufficient stock", null);
        }

        var id = await _ledger.HoldAsync(sku, quantity);
        return new ReservationResult(true, null, id);
    }

    public Task<int> AvailableAsync(string sku) => _ledger.CountAsync(sku);
}

public interface IStockLedger
{
    Task<int> CountAsync(string sku);
    Task<string> HoldAsync(string sku, int quantity);
}
