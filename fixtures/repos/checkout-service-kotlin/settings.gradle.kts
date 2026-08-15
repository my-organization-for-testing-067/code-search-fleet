rootProject.name = "checkout-service"

// com.acme:pricing-lib is published from the pricing-lib-java repo, not to any
// public index. When that repo is checked out beside this one -- which is what
// the fleet layout gives you, and what CI arranges -- Gradle substitutes the
// coordinate for the local build. Without it the dependency is unresolvable,
// so this is the line that makes the cross-repo edge in `cs deps` real rather
// than merely declared.
if (file("../pricing-lib-java").isDirectory) {
    includeBuild("../pricing-lib-java")
}
