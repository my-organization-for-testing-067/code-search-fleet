"""Hand-written mirror of the ReservationEvent proto contract.

Seam: the same contract is generated into web-monorepo-node as ReservationEvent.
Drift between the two is exactly the kind of cross-repo relation no single-repo
index can see.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ReservationEvent:
    order_id: str
    sku: str
    reservation_id: str

    @classmethod
    def from_json(cls, raw: bytes | str) -> "ReservationEvent":
        payload = json.loads(raw)
        return cls(
            order_id=payload["orderId"],
            sku=payload["sku"],
            reservation_id=payload["reservationId"],
        )
