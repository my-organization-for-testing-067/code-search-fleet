#!/usr/bin/env python3
"""Generate a synthetic fleet large enough for cost to be visible.

The point is not realism of *content* -- it is realism of *shape*: many repos,
many files, several languages, and a handful of genuine cross-repo seams buried
among files that merely look similar. A corpus of identical files would let an
engine cache its way to a flattering number.

What this deliberately does NOT reproduce: vendored dependency trees, generated
code, minified assets, and the decade of drift that makes real repos expensive.
Numbers from this corpus are a floor on cost, not an estimate of it.
"""
from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

# A few strings that exist across repos, so fleet-wide queries have something
# real to find rather than matching nothing at scale.
SEAMS = [
    "inventory.reserve.enabled",
    "/api/v1/inventory/reserve",
    "orders.reserved.v1",
    "reservationId",
]

LANGS = {
    "cs": """using System;
using Acme.{ns}.Domain;

namespace Acme.{ns}.Services;

// {comment}
public class {name}Service
{{
    private readonly IStore _store;
    private readonly IFeatureFlags _flags;

    public {name}Service(IStore store, IFeatureFlags flags)
    {{
        _store = store;
        _flags = flags;
    }}

    public bool Handle{name}(string id, int quantity)
    {{
        if (!_flags.IsEnabled("{seam}")) return false;
        var record = _store.Load(id);
        if (record is null) return false;
        return _store.Apply(record, quantity);
    }}

    public string Describe() => $"{name} handler for {{_store}}";
}}
""",
    "py": '''"""{comment}"""

from dataclasses import dataclass


TOPIC = "{seam}"


@dataclass
class {name}Record:
    order_id: str
    sku: str
    quantity: int


class {name}Handler:
    def __init__(self, store, flags):
        self._store = store
        self._flags = flags

    def handle(self, record: {name}Record) -> bool:
        if not self._flags.is_enabled(TOPIC):
            return False
        existing = self._store.load(record.order_id)
        if existing is None:
            return False
        return self._store.apply(existing, record.quantity)
''',
    "kt": """package com.acme.{ns}

// {comment}
private const val {NAME}_PATH = "{seam}"

class {name}Handler(
    private val store: Store,
    private val flags: FeatureFlags,
) {{
    fun handle(id: String, quantity: Int): Boolean {{
        if (!flags.isEnabled({NAME}_PATH)) return false
        val record = store.load(id) ?: return false
        return store.apply(record, quantity)
    }}

    fun describe(): String = "{name} handler"
}}
""",
    "ts": """// {comment}
export const {NAME}_KEY = "{seam}";

export interface {name}Record {{
  orderId: string;
  sku: string;
  quantity: number;
}}

export class {name}Handler {{
  constructor(
    private readonly store: Store,
    private readonly flags: FeatureFlags,
  ) {{}}

  handle(record: {name}Record): boolean {{
    if (!this.flags.isEnabled({NAME}_KEY)) return false;
    const existing = this.store.load(record.orderId);
    if (!existing) return false;
    return this.store.apply(existing, record.quantity);
  }}
}}
""",
    "java": """package com.acme.{ns};

// {comment}
public class {name}Handler {{
    public static final String KEY = "{seam}";

    private final Store store;
    private final FeatureFlags flags;

    public {name}Handler(Store store, FeatureFlags flags) {{
        this.store = store;
        this.flags = flags;
    }}

    public boolean handle(String id, int quantity) {{
        if (!flags.isEnabled(KEY)) return false;
        Object record = store.load(id);
        if (record == null) return false;
        return store.apply(record, quantity);
    }}
}}
""",
}

NOUNS = ["Order", "Reserve", "Ledger", "Pick", "Ship", "Invoice", "Refund",
         "Catalog", "Price", "Batch", "Route", "Audit", "Tenant", "Session"]
VERBS = ["Sync", "Apply", "Resolve", "Dispatch", "Reconcile", "Emit",
         "Validate", "Expire", "Archive", "Rebuild"]


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: gen_corpus.py <fleet-dir> <repos> <files-per-repo>", file=sys.stderr)
        return 2
    fleet = Path(sys.argv[1])
    n_repos = int(sys.argv[2])
    n_files = int(sys.argv[3])
    rng = random.Random(20260815)

    fleet.mkdir(parents=True, exist_ok=True)
    exts = list(LANGS)

    for r in range(n_repos):
        lang = exts[r % len(exts)]
        repo = fleet / f"service-{r:02d}-{lang}"
        src = repo / "src" / "main"
        src.mkdir(parents=True, exist_ok=True)

        for f in range(n_files):
            name = f"{rng.choice(NOUNS)}{rng.choice(VERBS)}{f}"
            # Only a minority of files carry a real seam, so a fleet-wide query
            # has to actually scan rather than hit on the first file.
            seam = rng.choice(SEAMS) if rng.random() < 0.05 else f"internal.key.{f}"
            body = LANGS[lang].format(
                ns=f"Svc{r:02d}",
                name=name,
                NAME=name.upper(),
                seam=seam,
                comment=f"Handler {f} in service {r}. {rng.choice(NOUNS).lower()} path.",
            )
            # Spread across directories; one flat folder of 2000 files is not
            # what a real repo looks like and it flatters directory traversal.
            sub = src / f"pkg{f % 40:02d}"
            sub.mkdir(exist_ok=True)
            (sub / f"{name}.{lang}").write_text(body)

        manifest = {
            "cs": ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                   "<TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>"),
            "py": f'[project]\nname = "service-{r:02d}"\nversion = "1.0.0"\n',
            "kt": 'plugins { kotlin("jvm") version "2.0.0" }\n',
            "ts": f'{{"name": "@acme/service-{r:02d}", "version": "1.0.0"}}\n',
            "java": "plugins {\n    `java-library`\n}\n",
        }[lang]
        fname = {"cs": "Service.csproj", "py": "pyproject.toml",
                 "kt": "build.gradle.kts", "ts": "package.json",
                 "java": "build.gradle.kts"}[lang]
        (repo / fname).write_text(manifest)

        # Real git history, because cs history walks it and an empty repo would
        # make that query look free.
        subprocess.run(["git", "init", "--quiet", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=b@e.example",
             "-c", "user.name=Bench", "commit", "--quiet", "-m", f"Import service-{r:02d}"],
            check=True,
        )
        print(f"  service-{r:02d}-{lang}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
