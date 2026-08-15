package com.acme.pricing;

import java.util.List;

/** Consumed by checkout-service-kotlin via PriceCalculator. */
public class DiscountEngine {

    private final List<DiscountRule> rules;

    public DiscountEngine(List<DiscountRule> rules) {
        this.rules = rules;
    }

    public long applyAll(List<LineItem> items) {
        long total = 0;
        for (LineItem item : items) {
            total += priceFor(item);
        }
        return total;
    }

    private long priceFor(LineItem item) {
        long line = item.quantity() * item.unitPriceCents();
        for (DiscountRule rule : rules) {
            if (rule.appliesTo(item)) {
                line = rule.apply(line);
            }
        }
        return line;
    }
}
