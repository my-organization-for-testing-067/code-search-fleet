package com.acme.pricing;

public record LineItem(String sku, int quantity, long unitPriceCents) {}
