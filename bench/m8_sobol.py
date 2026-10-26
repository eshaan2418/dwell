"""M8 sensitivity: Sobol total-effect shares of night noise and summer peak temperature w.r.t. hidden
properties (glazing, frame, wall) and uncertain inputs, over rooms of the frozen TEST buildings.

Posteriors come from the hidden-property model trained on the train split; the heat analysis uses the
reference heat-wave week. Synthetic data (D-012).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bench.common import pmap, weather
from bench.synth_dataset import load, load_split
from bench.train_models import OUT as MODELS
from core.provenance import hash_paths, write_result
from core.scene import Unit
from hybrid.models import DwellModels
from hybrid.report import reference_periods
from hybrid.unit_sobol import HEAT_PARAMS, NOISE_PARAMS, room_sobol

N_ROOMS = 30


def _job(args: tuple) -> dict:
    obs_d, room_id, seed = args
    models = DwellModels.load(MODELS)
    u = Unit.from_dict(obs_d)
    post = models.hidden.posterior(u)
    ref = reference_periods(weather())
    t0 = ref["heatwave_start"]
    t0 = (t0.tz_localize("America/Toronto") if t0.tzinfo is None else t0).tz_convert("UTC")
    wk = weather().loc[t0 - pd.Timedelta(days=3) : t0 + pd.Timedelta(days=5)]
    return {"room": room_id, **room_sobol(u, room_id, post, wk, n_noise=128, n_heat=24, seed=seed)}


def main() -> None:
    test_b = set(load_split()["test_buildings"])
    recs = [r for r in load() if r["true"]["building_id"] in test_b]
    jobs = []
    for r in recs:
        u = Unit.from_dict(r["obs"])
        for room in u.rooms:
            if u.walls_of(room.id) and len(jobs) < N_ROOMS:
                jobs.append((r["obs"], room.id, len(jobs)))
    res = pmap(_job, jobs, workers=4)
    out = {}
    for tgt, params in (("noise", NOISE_PARAMS), ("heat", HEAT_PARAMS)):
        st = np.array([np.clip(x[tgt]["ST"], 0, None) for x in res])
        share = st / np.maximum(st.sum(1, keepdims=True), 1e-12)
        out[tgt] = {
            "params": params,
            "mean_total_effect": dict(zip(params, st.mean(0).round(4).tolist(), strict=True)),
            "mean_normalised_share": dict(zip(params, share.mean(0).round(4).tolist(), strict=True)),
            "hidden_property_share_mean": float(share[:, :3].sum(1).mean()),
            "median_output_sd": float(np.median([np.sqrt(x[tgt]["var"]) for x in res])),
            "n_rooms": len(res),
        }
    write_result(
        "m8/sobol.json",
        out,
        seed=0,
        config={"n_noise": 128, "n_heat": 24, "estimator": "Saltelli/Jansen"},
        data_hash=hash_paths(["data/synthetic/world_v1_split.json", "hybrid", "physics"]),
        data_kind="synthetic",
    )
    print(out)


if __name__ == "__main__":
    main()
