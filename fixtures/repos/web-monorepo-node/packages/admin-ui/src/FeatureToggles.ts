// Seam: these keys are read by the .NET inventory-api (IFeatureFlags.IsEnabled).
export const FLAG_INVENTORY_RESERVE = "inventory.reserve.enabled";
export const FLAG_CHECKOUT_EXPRESS = "checkout.express.enabled";

// Decoy: a retired flag whose key is a superstring of the live one. Substring
// matching reports it as the same flag; nothing reads it any more.
export const FLAG_INVENTORY_RESERVE_LEGACY = "inventory.reserve.enabled.legacy";

export interface FlagState {
  key: string;
  enabled: boolean;
  updatedBy: string;
}

export class FeatureToggleAdmin {
  constructor(private readonly api: { put(path: string, body: unknown): Promise<void> }) {}

  async setEnabled(key: string, enabled: boolean, actor: string): Promise<void> {
    await this.api.put(`/api/v1/flags/${key}`, { enabled, updatedBy: actor });
  }

  async disableReservations(actor: string): Promise<void> {
    await this.setEnabled(FLAG_INVENTORY_RESERVE, false, actor);
  }
}
