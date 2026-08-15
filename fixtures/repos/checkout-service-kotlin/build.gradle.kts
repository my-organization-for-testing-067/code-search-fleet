plugins {
    kotlin("jvm") version "2.0.0"
    kotlin("plugin.serialization") version "2.0.0"
}

repositories {
    mavenCentral()
}

dependencies {
    // Seam: consumes the pricing-lib-java repo.
    implementation("com.acme:pricing-lib:1.8.2")
    implementation("org.apache.kafka:kafka-clients:3.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.1")
    testImplementation(kotlin("test"))
}

// Pinned so the build does not depend on whichever JDK the machine or the CI
// runner defaults to. Kotlin and Java compiling against different targets is a
// confusing failure that says nothing about the code.
kotlin {
    jvmToolchain(21)
}
