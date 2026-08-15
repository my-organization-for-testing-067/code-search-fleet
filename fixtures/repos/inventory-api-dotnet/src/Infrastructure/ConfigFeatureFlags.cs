using Acme.Inventory.Domain;

namespace Acme.Inventory.Infrastructure;

public class ConfigFeatureFlags : IFeatureFlags
{
    private readonly IConfiguration _config;

    public ConfigFeatureFlags(IConfiguration config) => _config = config;

    // Flags default to on when absent; the admin UI writes the keys.
    public bool IsEnabled(string key) => _config.GetValue($"features:{key}", true);
}
