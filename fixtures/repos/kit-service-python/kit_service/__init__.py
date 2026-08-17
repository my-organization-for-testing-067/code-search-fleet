"""Assembles picking kits. Published to the internal index as kit-service."""

KIT_SERVICE_VERSION = "1.2.0"


def build_kit(order_id: str) -> dict:
    return {"orderId": order_id, "kit": []}
