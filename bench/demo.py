"""make demo: reports for two contrasting synthetic TEST units + one hypothetical unit on real Toronto
geodata, an index for the app, and measured report-generation times (results/m10/demo_timing.json)."""

from __future__ import annotations

import time

import numpy as np

from bench.common import weather
from bench.make_report import PUBLIC, report_for, update_index
from bench.synth_dataset import load, load_split
from bench.train_models import OUT as MODELS
from core.provenance import REPO, git_commit, write_result
from hybrid.models import DwellModels
from hybrid.report import generate

HYPOTHETICAL = REPO / "docs" / "templates" / "public_demo_floorplan.yaml"


def pick_units() -> list[str]:
    test_b = set(load_split()["test_buildings"])
    recs = [r for r in load() if r["true"]["building_id"] in test_b]

    # contrast: busiest-street unit vs quietest; prefer different orientations
    def street(r: dict) -> float:
        return max((x.get("aadt") or 0) for x in r["true"]["roads"]) if r["true"]["roads"] else 0.0

    recs = sorted(recs, key=street)
    return [recs[-1]["obs"]["id"], recs[0]["obs"]["id"]]


def main() -> None:
    timings = {}
    for uid in pick_units():
        t = time.time()
        report_for(uid)
        timings[uid] = time.time() - t
    if HYPOTHETICAL.exists():
        from recon.manual import unit_from_yaml

        t = time.time()
        try:
            u = unit_from_yaml(HYPOTHETICAL)
            rep = generate(
                u,
                DwellModels.load(MODELS),
                weather(),
                PUBLIC / u.id,
                "synthetic",
                label="Hypothetical unit on real Toronto geodata (no sensors)",
            )
            update_index({"id": u.id, "label": rep["unit"]["label"], "data_kind": "synthetic"})
            timings[u.id] = time.time() - t
        except Exception as e:  # network-dependent geodata
            print("hypothetical unit skipped:", e)
    write_result(
        "m10/demo_timing.json",
        {
            "report_seconds": timings,
            "max_seconds": float(np.max(list(timings.values()))),
            "machine": "Apple M5 Pro CPU (shared, loaded)",
            "commit": git_commit()["commit"],
        },
        seed=0,
        config={"units": list(timings)},
        data_hash="n/a",
        data_kind="synthetic",
    )
    print(timings)


if __name__ == "__main__":
    main()
