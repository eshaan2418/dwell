"""make predict UNIT=<id>: report bundle for a synthetic unit id, or a real pseudonym (private output)."""

from __future__ import annotations

import argparse
import json
import sys

from bench.common import weather
from bench.synth_dataset import load
from bench.train_models import OUT as MODELS
from core.provenance import REPO
from core.scene import Unit
from hybrid.models import DwellModels
from hybrid.report import generate

PUBLIC = REPO / "app" / "public" / "reports"
PRIVATE = REPO / "data" / "private"


def update_index(entry: dict) -> None:
    idx_p = PUBLIC / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else []
    idx = [e for e in idx if e["id"] != entry["id"]] + [entry]
    idx_p.parent.mkdir(parents=True, exist_ok=True)
    idx_p.write_text(json.dumps(idx, indent=1))


def report_for(unit_id: str, label: str | None = None, sobol: bool = True) -> dict:
    models = DwellModels.load(MODELS)
    recs = {r["obs"]["id"]: r for r in load()}
    if unit_id in recs:
        u = Unit.from_dict(recs[unit_id]["obs"])
        out = PUBLIC / unit_id
        rep = generate(u, models, weather(), out, "synthetic", label=label or f"Synthetic unit {unit_id}", sobol=sobol)
        update_index({"id": unit_id, "label": rep["unit"]["label"], "data_kind": "synthetic"})
        return rep
    uj = PRIVATE / "units" / unit_id / "unit.json"
    if not uj.exists():
        raise SystemExit(f"unknown unit {unit_id}: not synthetic and no {uj}")
    u = Unit.load(uj)
    # real homes: report stays private (share only with the occupant / with consent code F)
    return generate(u, models, weather(), PRIVATE / "reports" / unit_id, "real", label=label or unit_id, sobol=sobol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True)
    ap.add_argument("--no-sobol", action="store_true")
    a = ap.parse_args()
    rep = report_for(a.unit, sobol=not a.no_sobol)
    print(rep["unit"]["label"], "generated in", rep["provenance"]["generation_seconds"], "s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
