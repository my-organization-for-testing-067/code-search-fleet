# Runs the reservation API so the HTTP contract between this service and
# checkout-service-kotlin can be exercised rather than read. The ledger is
# in-memory (see PostgresStockLedger), so there is nothing else to bring up.
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY src/Acme.Inventory.csproj src/
RUN dotnet restore src/Acme.Inventory.csproj
COPY src/ src/
RUN dotnet publish src/Acme.Inventory.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Acme.Inventory.dll"]
