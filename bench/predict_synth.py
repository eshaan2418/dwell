"""Run physics predictions for every synthetic unit (cached), with leakage-safe posteriors.

Hidden-property posteriors for TRAIN units are cross-fitted (model fitted on the other train
building folds); TEST units use the model fitted on all train units. The test split is frozen
(data/synthetic/<name>_split.json) and never used for fitting anything.
"""

from __future__ import annotations

import argparse
import pickle
import zlib
from pathlib import Path

import numpy as np

from bench.common import ROOT, pmap, weather
from bench.synth_dataset import load, load_split
from core.scene import Unit
from hybrid.physics_predict import PredictOptions, predict_all
from hybrid.priors import HiddenPropertyModel

OUT = ROOT / "data" / "synthetic" / "cache"
N_FOLDS = 5


def building_folds(buildings: list[str], k: int = N_FOLDS, seed: int = 0) -> dict[str, int]:
    u = sorted(set(buildings))
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(u))
    return {u[i]: int(j % k) for j, i in enumerate(perm)}


def _job(args: tuple) -> tuple[str, dict]:
    rec, post_dict, opts, tag = args
    obs = Unit.from_dict(rec["obs"])
    from hybrid.priors import HiddenPosterior

    post = HiddenPosterior({k: np.array(v) for k, v in post_dict["glazing"].items()},
                           {k: np.array(v) for k, v in post_dict["frame"].items()}, np.array(post_dict["wall"]))
    # kit floor as measured during co-location (true floor + 0.5 dB estimation noise)
    rng = np.random.default_rng(zlib.crc32(obs.id.encode()))
    floor = {rid: float(v["mic_floor"] + v["cal_err_db"] + rng.normal(0, 0.5)) for rid, v in rec["kit"].items()}
    p = predict_all(obs, post, rec["start"], rec["days"], weather(), seed=zlib.crc32((obs.id + tag).encode()),
                    o=opts, kit_floor=floor)
    return obs.id, p


def posteriors(records: list[dict], test_b: set[str]) -> dict[str, dict]:
    train = [r for r in records if r["true"]["building_id"] not in test_b]
    folds = building_folds([r["true"]["building_id"] for r in train])
    out = {}
    full = HiddenPropertyModel().fit([(Unit.from_dict(r["true"]), Unit.from_dict(r["obs"])) for r in train])
    for k in range(N_FOLDS):
        m = HiddenPropertyModel().fit([(Unit.from_dict(r["true"]), Unit.from_dict(r["obs"])) for r in train
                                       if folds[r["true"]["building_id"]] != k])
        for r in train:
            if folds[r["true"]["building_id"]] == k:
                p = m.posterior(Unit.from_dict(r["obs"]))
                out[r["true"]["id"]] = p
    for r in records:
        if r["true"]["building_id"] in test_b:
            out[r["true"]["id"]] = full.posterior(Unit.from_dict(r["obs"]))
    return {k: {"glazing": {i: v.tolist() for i, v in p.glazing.items()},
                "frame": {i: v.tolist() for i, v in p.frame.items()}, "wall": p.wall.tolist()} for k, p in out.items()}


def run(name: str, tag: str, opts: PredictOptions) -> Path:
    path = OUT / f"{name}_pred_{tag}.pkl"
    if path.exists():
        return path
    recs = load(name)
    split = load_split(name)
    post = posteriors(recs, set(split["test_buildings"]))
    res = dict(pmap(_job, [(r, post[r["true"]["id"]], opts, tag) for r in recs]))
    with open(path, "wb") as f:
        pickle.dump(res, f)
    return path


VARIANTS = {
    "main": PredictOptions(),
    "no_obstruction": PredictOptions(use_obstruction=False, n_mc=4),
    "no_transit": PredictOptions(use_transit=False, n_mc=4),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="world_v1")
    ap.add_argument("--variants", default="main,no_obstruction,no_transit")
    a = ap.parse_args()
    for v in a.variants.split(","):
        print(v, run(a.name, v, VARIANTS[v]))


if __name__ == "__main__":
    main()
