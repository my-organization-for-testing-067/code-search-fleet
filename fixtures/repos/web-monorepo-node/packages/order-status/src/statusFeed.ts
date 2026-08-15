import { parseReservationEvent, type ReservationEvent } from "@acme/schemas";

export class OrderStatusFeed {
  private readonly reservations = new Map<string, ReservationEvent[]>();

  ingest(raw: string): void {
    const event = parseReservationEvent(raw);
    const existing = this.reservations.get(event.orderId) ?? [];
    existing.push(event);
    this.reservations.set(event.orderId, existing);
  }

  reservedSkus(orderId: string): string[] {
    return (this.reservations.get(orderId) ?? []).map((event) => event.sku);
  }
}
