package com.acme.pricing;

public class BulkDiscountRule implements DiscountRule {

    private final int threshold;
    private final int percentOff;

    public BulkDiscountRule(int threshold, int percentOff) {
        this.threshold = threshold;
        this.percentOff = percentOff;
    }

    @Override
    public boolean appliesTo(LineItem item) {
        return item.quantity() >= threshold;
    }

    @Override
    public long apply(long lineTotalCents) {
        return lineTotalCents - (lineTotalCents * percentOff / 100);
    }
}
