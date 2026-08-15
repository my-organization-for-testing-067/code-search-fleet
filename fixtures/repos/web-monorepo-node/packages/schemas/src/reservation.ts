// Seam: generated from the ReservationEvent proto contract; the Python
// fulfillment-worker keeps a hand-written mirror of the same shape.

export interface ReservationEvent {
  orderId: string;
  sku: string;
  reservationId: string;
}

export function parseReservationEvent(raw: string): ReservationEvent {
  const payload = JSON.parse(raw) as Partial<ReservationEvent>;
  if (!payload.orderId || !payload.sku || !payload.reservationId) {
    throw new Error("malformed ReservationEvent");
  }
  return payload as ReservationEvent;
}
