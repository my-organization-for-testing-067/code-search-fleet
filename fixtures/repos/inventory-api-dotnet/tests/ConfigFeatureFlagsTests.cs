using Acme.Inventory.Infrastructure;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Acme.Inventory.Tests;

public class ConfigFeatureFlagsTests
{
    private static ConfigFeatureFlags Flags(params (string Key, string Value)[] settings)
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(settings.Select(s =>
                new KeyValuePair<string, string?>(s.Key, s.Value)))
            .Build();
        return new ConfigFeatureFlags(config, NullLogger<ConfigFeatureFlags>.Instance);
    }

    [Fact]
    public void ReturnsTrue_WhenFlagIsSetTrue()
    {
        var flags = Flags(("features:inventory.reserve.enabled", "true"));
        Assert.True(flags.IsEnabled("inventory.reserve.enabled"));
    }

    [Fact]
    public void ReturnsFalse_WhenFlagIsSetFalse()
    {
        var flags = Flags(("features:inventory.reserve.enabled", "false"));
        Assert.False(flags.IsEnabled("inventory.reserve.enabled"));
    }

    // Added by the fix. Its absence is what let the fail-open default through
    // review: every existing test set the key explicitly, so no test ever
    // exercised the branch that actually shipped to production.
    [Fact]
    public void ReturnsFalse_WhenFlagIsAbsent()
    {
        var flags = Flags(("features:something.else", "true"));
        Assert.False(flags.IsEnabled("inventory.reserve.enabled"));
    }

    [Fact]
    public void ReturnsFalse_WhenConfigurationSectionIsRenamed()
    {
        // The exact production shape: the section moved to featureFlags:.
        var flags = Flags(("featureFlags:inventory.reserve.enabled", "false"));
        Assert.False(flags.IsEnabled("inventory.reserve.enabled"));
    }
}
