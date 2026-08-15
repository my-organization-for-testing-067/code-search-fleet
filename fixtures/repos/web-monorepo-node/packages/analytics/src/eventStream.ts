// Decoy: subscribes to orders.reserved.v2, which NO repo produces -- the
// producer still emits v1. This models a real bug (an orphaned consumer left
// behind by a version bump). A tool that links this to the Kotlin publisher is
// reporting a relationship that does not exist.

const ANALYTICS_TOPIC = "orders.reserved.v2";

export interface ReservationMetric {
  orderId: string;
  sku: string;
  observedAt: string;
}

export class ReservationMetrics {
  private readonly seen: ReservationMetric[] = [];

  constructor(private readonly subscribe: (topic: string, handler: (raw: string) => void) => void) {
    this.subscribe(ANALYTICS_TOPIC, (raw) => this.record(raw));
  }

  private record(raw: string): void {
    const payload = JSON.parse(raw) as { orderId: string; sku: string };
    this.seen.push({ ...payload, observedAt: new Date().toISOString() });
  }

  count(): number {
    return this.seen.length;
  }
}
