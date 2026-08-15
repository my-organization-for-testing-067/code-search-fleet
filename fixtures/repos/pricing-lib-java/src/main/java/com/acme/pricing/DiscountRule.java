package com.acme.pricing;

public interface DiscountRule {
    boolean appliesTo(LineItem item);

    long apply(long lineTotalCents);
}
