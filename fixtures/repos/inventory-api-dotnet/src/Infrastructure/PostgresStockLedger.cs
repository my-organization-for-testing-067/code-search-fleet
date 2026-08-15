using System.Collections.Concurrent;

namespace Acme.Inventory.Infrastructure;

// In-memory stand-in for the real ledger. Enough to make the service run.
public class PostgresStockLedger : IStockLedger
{
    private readonly ConcurrentDictionary<string, int> _stock = new()
    {
        ["SKU-1"] = 10,
        ["SKU-2"] = 3,
    };

    private readonly ConcurrentDictionary<string, (string Sku, int Quantity)> _holds = new();

    public Task<int> CountAsync(string sku) =>
        Task.FromResult(_stock.TryGetValue(sku, out var n) ? n : 0);

    public Task<string> HoldAsync(string sku, int quantity)
    {
        _stock.AddOrUpdate(sku, 0, (_, current) => current - quantity);
        var id = Guid.NewGuid().ToString("n");
        _holds[id] = (sku, quantity);
        return Task.FromResult(id);
    }

    public Task ReleaseAsync(string reservationId)
    {
        if (_holds.TryRemove(reservationId, out var hold))
        {
            _stock.AddOrUpdate(hold.Sku, hold.Quantity, (_, current) => current + hold.Quantity);
        }
        return Task.CompletedTask;
    }
}
