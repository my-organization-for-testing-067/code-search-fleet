package com.acme.checkout

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.net.URI

// Seam: this path string is the only link to the .NET inventory-api route.
private const val RESERVE_PATH = "/api/v1/inventory/reserve"

class InventoryClient(
    private val baseUrl: String,
    private val http: HttpClient = HttpClient.newHttpClient(),
) {
    fun reserve(sku: String, quantity: Int): ReservationResponse {
        val body = """{"sku":"$sku","quantity":$quantity}"""
        val request = HttpRequest.newBuilder()
            .uri(URI.create("$baseUrl$RESERVE_PATH"))
            .header("content-type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build()

        val response = http.send(request, HttpResponse.BodyHandlers.ofString())
        return when (response.statusCode()) {
            200 -> ReservationResponse.Reserved(parseReservationId(response.body()))
            409 -> ReservationResponse.OutOfStock
            503 -> ReservationResponse.Disabled
            else -> throw IllegalStateException("reserve failed: ${response.statusCode()}")
        }
    }

    // Parsed as JSON rather than matched as text: the upstream serializer is
    // free to change whitespace, field order, or escaping without notice.
    private fun parseReservationId(payload: String): String =
        Json.parseToJsonElement(payload).jsonObject["reservationId"]?.jsonPrimitive?.content
            ?: error("no reservationId in response")
}

sealed interface ReservationResponse {
    data class Reserved(val reservationId: String) : ReservationResponse
    data object OutOfStock : ReservationResponse
    data object Disabled : ReservationResponse
}
