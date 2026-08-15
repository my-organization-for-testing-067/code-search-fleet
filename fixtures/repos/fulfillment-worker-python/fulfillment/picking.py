from collections import defaultdict

from fulfillment.contracts import ReservationEvent


class PickListBuilder:
    """Groups reservations into per-order pick lists."""

    def __init__(self, warehouse_client) -> None:
        self._warehouse = warehouse_client
        self._pending: dict[str, list[ReservationEvent]] = defaultdict(list)

    def add(self, event: ReservationEvent) -> None:
        self._pending[event.order_id].append(event)
        if self._is_complete(event.order_id):
            self.flush(event.order_id)

    def flush(self, order_id: str) -> None:
        events = self._pending.pop(order_id, [])
        if events:
            self._warehouse.submit_pick_list(order_id, [e.sku for e in events])

    def _is_complete(self, order_id: str) -> bool:
        return self._warehouse.expected_line_count(order_id) == len(self._pending[order_id])
