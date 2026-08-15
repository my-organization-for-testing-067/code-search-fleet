from collections import defaultdict

from fulfillment.contracts import ReservationEvent


class PickListBuilder:
    """Groups reservations into per-order pick lists."""

    def __init__(self, warehouse_client) -> None:
        self._warehouse = warehouse_client
        self._pending: dict[str, dict[str, ReservationEvent]] = defaultdict(dict)
        self._submitted: set[str] = set()

    def add(self, event: ReservationEvent) -> None:
        # Kafka delivers at least once, so the same reservation can arrive more
        # than once. Keying by reservation_id makes a redelivery replace the
        # earlier copy instead of counting as a second line, and orders already
        # submitted are ignored outright -- a redelivery arriving after the
        # pick list was sent must not send it again.
        if event.order_id in self._submitted:
            return

        self._pending[event.order_id][event.reservation_id] = event
        if self._is_complete(event.order_id):
            self.flush(event.order_id)

    def flush(self, order_id: str) -> None:
        events = self._pending.pop(order_id, {})
        if events:
            self._warehouse.submit_pick_list(
                order_id, [e.sku for e in events.values()]
            )
            self._submitted.add(order_id)

    def _is_complete(self, order_id: str) -> bool:
        return self._warehouse.expected_line_count(order_id) == len(self._pending[order_id])
