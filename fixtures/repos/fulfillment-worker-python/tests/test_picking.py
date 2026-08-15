from fulfillment.contracts import ReservationEvent
from fulfillment.picking import PickListBuilder


class FakeWarehouse:
    def __init__(self, expected: int) -> None:
        self._expected = expected
        self.submitted: list[tuple[str, list[str]]] = []

    def expected_line_count(self, order_id: str) -> int:
        return self._expected

    def submit_pick_list(self, order_id: str, skus: list[str]) -> None:
        self.submitted.append((order_id, skus))


def event(sku: str, reservation_id: str) -> ReservationEvent:
    return ReservationEvent(order_id="order-1", sku=sku, reservation_id=reservation_id)


def test_submits_when_all_lines_arrive():
    warehouse = FakeWarehouse(expected=2)
    builder = PickListBuilder(warehouse)

    builder.add(event("SKU-1", "r1"))
    builder.add(event("SKU-2", "r2"))

    assert warehouse.submitted == [("order-1", ["SKU-1", "SKU-2"])]


def test_does_not_submit_before_all_lines_arrive():
    warehouse = FakeWarehouse(expected=2)
    builder = PickListBuilder(warehouse)

    builder.add(event("SKU-1", "r1"))

    assert warehouse.submitted == []


# Added by the fix. Every earlier test fed distinct reservations, so none
# described what happens under the at-least-once delivery the consumer
# actually runs on.
def test_redelivered_event_does_not_complete_the_order_early():
    warehouse = FakeWarehouse(expected=2)
    builder = PickListBuilder(warehouse)

    builder.add(event("SKU-1", "r1"))
    builder.add(event("SKU-1", "r1"))  # same reservation, delivered twice

    assert warehouse.submitted == []


def test_redelivery_after_completion_does_not_submit_twice():
    warehouse = FakeWarehouse(expected=2)
    builder = PickListBuilder(warehouse)

    builder.add(event("SKU-1", "r1"))
    builder.add(event("SKU-2", "r2"))
    # The whole order is redelivered after the pick list was already sent.
    builder.add(event("SKU-1", "r1"))
    builder.add(event("SKU-2", "r2"))

    assert len(warehouse.submitted) == 1
