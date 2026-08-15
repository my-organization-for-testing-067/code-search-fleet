package com.acme.checkout

import kotlin.test.Test
import kotlin.test.assertEquals

class InventoryClientTest {

    private fun parse(payload: String): String {
        val client = InventoryClient("http://localhost")
        val method = InventoryClient::class.java
            .getDeclaredMethod("parseReservationId", String::class.java)
        method.isAccessible = true
        return method.invoke(client, payload) as String
    }

    @Test
    fun `reads the reservation id from a compact response`() {
        val payload = """{"succeeded":true,"reason":null,"reservationId":"abc123"}"""
        assertEquals("abc123", parse(payload))
    }

    // Added by the fix. Every earlier test used the compact form produced by
    // one specific serializer setting, so no test described what the client
    // actually required of the response.
    @Test
    fun `reads the reservation id when the response is indented`() {
        val payload = """
            {
              "succeeded": true,
              "reason": null,
              "reservationId": "abc123"
            }
        """.trimIndent()
        assertEquals("abc123", parse(payload))
    }

    @Test
    fun `reads the reservation id regardless of field order`() {
        val payload = """{"reservationId":"abc123","succeeded":true}"""
        assertEquals("abc123", parse(payload))
    }
}
