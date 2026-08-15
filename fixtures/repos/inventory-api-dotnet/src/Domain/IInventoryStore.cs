namespace Acme.Inventory.Domain;

public interface IInventoryStore
{
    Task<ReservationResult> ReserveAsync(string sku, int quantity);
    Task ReleaseAsync(string reservationId);
    Task<int> AvailableAsync(string sku);
}

public record ReservationResult(bool Succeeded, string? Reason, string? ReservationId);

public interface IFeatureFlags
{
    bool IsEnabled(string key);
}
