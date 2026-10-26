"""Freeze real test units (run ONCE when >= 3 real units with sensor targets exist).

Picks ~1/3 of real buildings (seeded) as test units, writes data/splits/real_test_units.json with a sha256
checksum of the sorted pseudonymous IDs. Re-running never changes an existing freeze.
"""

from __future__ import annotations

import hashlib
import json
import sys

import numpy as np

from core.provenance import REPO

PRIVATE = REPO / "data" / "private"
OUT = REPO / "data" / "splits" / "real_test_units.json"


def main() -> int:
    if OUT.exists():
        d = json.loads(OUT.read_text())
        ok = hashlib.sha256(",".join(d["test_units"]).encode()).hexdigest() == d["sha256"]
        print("already frozen:", d["sha256"][:12], "checksum OK" if ok else "CHECKSUM MISMATCH")
        return 0 if ok else 1
    units = sorted(p.stem for p in (PRIVATE / "targets").glob("*.pkl")) if (PRIVATE / "targets").exists() else []
    if len(units) < 3:
        print(f"only {len(units)} real units with targets; need >= 3 (awaiting-human)")
        return 0
    import pandas as pd

    meta = pd.read_csv(PRIVATE / "units.csv")
    bld = {r.unit_pid: str(getattr(r, "building_pid", r.unit_pid)) for r in meta.itertuples()}
    buildings = sorted({bld.get(u, u) for u in units})
    rng = np.random.default_rng(20261024)
    k = max(1, round(len(buildings) / 3))
    test_b = set(rng.choice(buildings, k, replace=False).tolist())
    test = sorted(u for u in units if bld.get(u, u) in test_b)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"test_units": test, "sha256": hashlib.sha256(",".join(test).encode()).hexdigest(), "n_units": len(units)},
            indent=1,
        )
    )
    print("froze", len(test), "real test units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
