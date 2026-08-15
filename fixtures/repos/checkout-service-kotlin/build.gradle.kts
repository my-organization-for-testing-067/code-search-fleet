plugins {
    kotlin("jvm") version "2.0.0"
}

dependencies {
    // Seam: consumes the pricing-lib-java repo.
    implementation("com.acme:pricing-lib:1.8.2")
    implementation("org.apache.kafka:kafka-clients:3.7.0")
}
