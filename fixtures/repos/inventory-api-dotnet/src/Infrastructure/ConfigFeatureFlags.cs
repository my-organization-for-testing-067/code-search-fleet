using Acme.Inventory.Domain;

namespace Acme.Inventory.Infrastructure;

public class ConfigFeatureFlags : IFeatureFlags
{
    private readonly IConfiguration _config;
    private readonly ILogger<ConfigFeatureFlags> _log;

    public ConfigFeatureFlags(IConfiguration config, ILogger<ConfigFeatureFlags> log)
    {
        _config = config;
        _log = log;
    }

    // A missing key fails closed. Defaulting to enabled meant that renaming the
    // configuration section silently turned every guarded feature back on.
    public bool IsEnabled(string key)
    {
        var value = _config.GetValue<bool?>($"features:{key}");
        if (value is null)
        {
            _log.LogWarning(
                "feature flag {Key} is absent from configuration; treating as disabled", key);
            return false;
        }

        return value.Value;
    }
}
