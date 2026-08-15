"""Decoy: an unrelated DiscountEngine.

Shares a name with com.acme.pricing.DiscountEngine in pricing-lib-java, but is
a different thing entirely -- this one prices warehouse handling fees and is
never exposed to checkout. A tool that links these two by name alone is
conflating unrelated symbols.
"""


class DiscountEngine:
    """Applies handling-fee waivers to pick lists."""

    def __init__(self, waiver_threshold_cents: int) -> None:
        self._threshold = waiver_threshold_cents

    def handling_fee_cents(self, line_count: int, subtotal_cents: int) -> int:
        if subtotal_cents >= self._threshold:
            return 0
        return 250 + (50 * max(0, line_count - 1))
