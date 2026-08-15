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

    // Decoy: no repo in the fleet calls this. A tool naming a consumer for it
    // is inventing one; "is this endpoint dead?" is a real question worth
    // being able to answer correctly.
    [HttpPost("release")]
    public async Task<IActionResult> Release([FromBody] ReleaseRequest request)
    {
        await _store.ReleaseAsync(request.ReservationId);
        return NoContent();
    }
}

public record ReserveRequest(string Sku, int Quantity);

public record ReleaseRequest(string ReservationId);
