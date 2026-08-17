using System;

namespace Acme.Inventory.Infrastructure;

// This file exists to make two edge kinds DISTINGUISHABLE in the fixture.
//
// C# has one syntax for both relations -- `class Foo : BaseFoo, IFoo` -- so an
// extractor cannot separate base-class inheritance from interface
// implementation without resolving each name in the base list. Before this
// file, every C# type in the fixture implemented an interface and none extended
// a base class, so a graph reporting `implements: 0` was indistinguishable from
// one that had filed all three relations under `extends`. Both produce the same
// count, and BASELINE.md drew the stronger of the two conclusions from it.
//
// LedgerBase gives the fixture a genuine base class, and AuditedStockLedger
// does BOTH at once, which is the case that actually separates the two.
public abstract class LedgerBase
{
    protected DateTime LastAudited { get; set; }

    public abstract int Available(string sku);
}

public class AuditedStockLedger : LedgerBase, IStockLedger
{
    private readonly PostgresStockLedger _inner = new PostgresStockLedger();

    public override int Available(string sku)
    {
        LastAudited = DateTime.UtcNow;
        return _inner.Available(sku);
    }
}
