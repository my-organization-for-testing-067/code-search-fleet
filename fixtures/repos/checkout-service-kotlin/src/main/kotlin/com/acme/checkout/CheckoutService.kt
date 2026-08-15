package com.acme.checkout

class CheckoutService(
    private val inventory: InventoryClient,
    private val events: EventPublisher,
    private val pricing: PriceCalculator,
) {
    fun checkout(cart: Cart): CheckoutResult {
        val total = pricing.totalFor(cart.lines)

        for (line in cart.lines) {
            when (val response = inventory.reserve(line.sku, line.quantity)) {
                is ReservationResponse.Reserved ->
                    events.publishReserved(cart.orderId, line.sku, response.reservationId)
                ReservationResponse.OutOfStock -> return CheckoutResult.Rejected(line.sku)
                ReservationResponse.Disabled -> return CheckoutResult.Unavailable
            }
        }

        return CheckoutResult.Accepted(cart.orderId, total)
    }
}

data class Cart(val orderId: String, val lines: List<CartLine>)
data class CartLine(val sku: String, val quantity: Int, val unitPriceCents: Long)

sealed interface CheckoutResult {
    data class Accepted(val orderId: String, val totalCents: Long) : CheckoutResult
    data class Rejected(val sku: String) : CheckoutResult
    data object Unavailable : CheckoutResult
}
