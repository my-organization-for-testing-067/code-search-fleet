using Acme.Inventory.Domain;
using Acme.Inventory.Infrastructure;

var builder = WebApplication.CreateBuilder(args);

builder.Services
    .AddControllers()
    .AddJsonOptions(options => options.JsonSerializerOptions.WriteIndented = true);

// The only place the concrete implementations are named. A static call graph
// cannot connect ReservationController._store to SqlInventoryStore through this.
builder.Services.AddScoped<IInventoryStore, SqlInventoryStore>();
builder.Services.AddScoped<IStockLedger, PostgresStockLedger>();
builder.Services.AddSingleton<IFeatureFlags, ConfigFeatureFlags>();

var app = builder.Build();
app.MapControllers();
app.Run();
