// Seam: a SECOND consumer of the .NET inventory reserve endpoint. A tool that
// reports only the Kotlin caller has a recall failure -- the dangerous kind,
// since it means "I changed the API and updated every caller" is wrong.

const RESERVE_ENDPOINT = "/api/v1/inventory/reserve";

export class RestockTool {
  constructor(
    private readonly baseUrl: string,
    private readonly fetchFn: typeof fetch = fetch,
  ) {}

  async reserveForRestock(sku: string, quantity: number): Promise<boolean> {
    const response = await this.fetchFn(`${this.baseUrl}${RESERVE_ENDPOINT}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sku, quantity }),
    });
    return response.status === 200;
  }
}
