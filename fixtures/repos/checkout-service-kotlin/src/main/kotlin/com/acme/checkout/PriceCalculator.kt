package com.acme.checkout

import com.acme.pricing.DiscountEngine
import com.acme.pricing.LineItem

// Seam: depends on the pricing-lib-java repo (com.acme:pricing-lib).
class PriceCalculator(private val discounts: DiscountEngine) {
    fun totalFor(lines: List<CartLine>): Long {
        val items = lines.map { LineItem(it.sku, it.quantity, it.unitPriceCents) }
        return discounts.applyAll(items)
    }
}
