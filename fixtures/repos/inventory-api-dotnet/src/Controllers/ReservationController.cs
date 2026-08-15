using Microsoft.AspNetCore.Mvc;
using Acme.Inventory.Domain;

namespace Acme.Inventory.Controllers;

[ApiController]
[Route("api/v1/inventory")]
public class ReservationController : ControllerBase
{
    private readonly IInventoryStore _store;
    private readonly IFeatureFlags _flags;

    public ReservationController(IInventoryStore store, IFeatureFlags flags)
    {
        _store = store;
        _flags = flags;
    }

    [HttpPost("reserve")]
    public async Task<IActionResult> Reserve([FromBody] ReserveRequest request)
    {
        if (!_flags.IsEnabled("inventory.reserve.enabled"))
        {
            return StatusCode(503, "reservations disabled");
        }

        var result = await _store.ReserveAsync(request.Sku, request.Quantity);
        return result.Succeeded ? Ok(result) : Conflict(result.Reason);
    }
}

public record ReserveRequest(string Sku, int Quantity);
