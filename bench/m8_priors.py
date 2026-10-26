"""M8 contribution 1: hidden-property inference accuracy on frozen TEST units (synthetic).

Compares the full model (metadata + visual cues) with ablations (no cues, no metadata) and the
'default materials' assignment. Log-loss is reported for probabilistic calibration.
"""

from __future__ import annotations

from bench.synth_dataset import load, load_split
from core.provenance import hash_paths, write_result
from core.scene import Unit
from hybrid.priors import HiddenPropertyModel, evaluate, evaluate_default


def main() -> None:
    test_b = set(load_split()["test_buildings"])
    recs = load()
    tr = [(Unit.from_dict(r["true"]), Unit.from_dict(r["obs"])) for r in recs if r["true"]["building_id"] not in test_b]
    te = [(Unit.from_dict(r["true"]), Unit.from_dict(r["obs"])) for r in recs if r["true"]["building_id"] in test_b]
    m = HiddenPropertyModel().fit(tr)
    out = {
        "n_train_units": len(tr), "n_test_units": len(te),
        "full": evaluate(m, te), "no_cues": evaluate(m, te, use_cues=False),
        "no_metadata": evaluate(m, te, use_metadata=False), "default_materials": evaluate_default(te),
    }
    write_result("m8/hidden_properties.json", out, seed=7, config={"alpha": m.alpha},
                 data_hash=hash_paths(["data/synthetic/world_v1_split.json", "synth"]), data_kind="synthetic")
    print(out)


if __name__ == "__main__":
    main()
