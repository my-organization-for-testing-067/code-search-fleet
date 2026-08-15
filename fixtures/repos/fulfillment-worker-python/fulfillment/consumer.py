"""Consumes reservation events produced by checkout-service-kotlin.

Upstream, checkout reserves stock through POST /api/v1/inventory/reserve before
publishing here. This worker never calls that endpoint itself -- the mention is
prose only, and a tool that counts it as a call site is matching text rather
than code.
"""

from kafka import KafkaConsumer

from fulfillment.contracts import ReservationEvent
from fulfillment.picking import PickListBuilder

# Seam: matches ORDERS_RESERVED_TOPIC in checkout-service-kotlin.
ORDERS_RESERVED_TOPIC = "orders.reserved.v1"
CONSUMER_GROUP = "fulfillment-worker"


class ReservationConsumer:
    def __init__(self, brokers: list[str], builder: PickListBuilder) -> None:
        self._consumer = KafkaConsumer(
            ORDERS_RESERVED_TOPIC,
            bootstrap_servers=brokers,
            group_id=CONSUMER_GROUP,
            enable_auto_commit=False,
        )
        self._builder = builder

    def run(self) -> None:
        for message in self._consumer:
            event = ReservationEvent.from_json(message.value)
            self._builder.add(event)
            self._consumer.commit()
