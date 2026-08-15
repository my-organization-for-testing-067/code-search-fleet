package com.acme.checkout

import org.apache.kafka.clients.producer.KafkaProducer
import org.apache.kafka.clients.producer.ProducerRecord

// Seam: this topic name is the only link to the Python fulfillment-worker.
const val ORDERS_RESERVED_TOPIC = "orders.reserved.v1"

class EventPublisher(private val producer: KafkaProducer<String, String>) {
    fun publishReserved(orderId: String, sku: String, reservationId: String) {
        // Payload shape is the ReservationEvent proto contract.
        val payload = """{"orderId":"$orderId","sku":"$sku","reservationId":"$reservationId"}"""
        producer.send(ProducerRecord(ORDERS_RESERVED_TOPIC, orderId, payload))
    }
}
