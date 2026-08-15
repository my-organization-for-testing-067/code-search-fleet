plugins {
    `java-library`
    `maven-publish`
}

// What this repo publishes. Consumers name this coordinate, which is the only
// thing tying them back here.
group = "com.acme"
version = "1.8.2"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

publishing {
    publications {
        create<MavenPublication>("maven") {
            artifactId = "pricing-lib"
            from(components["java"])
        }
    }
}
