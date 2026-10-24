"""Build the synthetic evaluation world (M2): units, simulated sensor deployments, derived targets.

Output (git-ignored cache, deterministic from seed): data/synthetic/cache/<name>/<unit>.pkl
Frozen split (committed): data/synthetic/<name>_split.json with a checksum of the test building IDs.

Usage: python -m bench.synth_dataset [--name world_v1] [--buildings 160] [--seed 7] [--days 21]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from bench.common import ROOT, pmap, weather
from ingest.targets import TZ, daily_heat, daily_sun_hours, nightly_noise, window_open_nights
from synth.generator import generate_world, observe
from synth.truth import Deployment, simulate_unit

CACHE = ROOT / "data" / "synthetic" / "cache"


def deployment_for(rng: np.random.Generator) -> pd.Timestamp:
    # 50 % summer (heat target), 50 % spread over the rest of 2025
    if rng.random() < 0.5:
        d = pd.Timestamp("2025-06-01") + pd.Timedelta(days=int(rng.integers(0, 75)))
    else:
        d = pd.Timestamp("2025-01-03") + pd.Timedelta(days=int(rng.integers(0, 330)))
    return pd.Timestamp(d.date(), tz=TZ)


def _build(args: tuple[str, int, int, int, int]) -> str:
    name, seed, n_buildings, idx, days = args
    out_path = CACHE / name / f"{idx:05d}.pkl"
    if out_path.exists():
        return str(out_path)
    units = generate_world(seed, n_buildings)
    u = units[idx]
    rng = np.random.default_rng([seed, idx])
    start = deployment_for(rng)
    sim = simulate_unit(rng, u, weather(), Deployment(start, days))
    obs = observe(rng, u)
    targets = {}
    for rid, d in sim["rooms"].items():
        noise = nightly_noise(d)
        if len(noise):
            noise["open_heur"] = window_open_nights(d, weather()["temp_c"], noise).reindex(noise.index).fillna(False)
            om = sim["truth"][rid]["open_window_minutes"]
            ol = om.copy()
            ol.index = (ol.index.tz_convert(TZ) - pd.Timedelta(hours=12)).normalize().date
            noise["open_true"] = ol.groupby(level=0).max().reindex(noise.index).fillna(False).astype(bool)
        tr = sim["truth"][rid]["true_sensor_sun_min"].copy()
        tr.index = tr.index.tz_convert(TZ)
        sun = daily_sun_hours(d, u.lat, u.lon)
        sun["sun_h_true"] = (tr.groupby(tr.index.date).sum() / 60.0).reindex(sun.index)
        targets[rid] = {"sun": sun, "noise": noise, "heat": daily_heat(d)}
    rec = {"true": u.to_dict(), "obs": obs.to_dict(), "start": start, "days": days, "targets": targets,
           "kit": sim["kit"], "behaviour": sim["behaviour"]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(rec, f)
    return str(out_path)


def split(name: str, units_buildings: list[str], seed: int, test_frac: float = 0.2) -> dict:
    blds = sorted(set(units_buildings))
    rng = np.random.default_rng(seed + 991)
    test = sorted(rng.choice(blds, int(round(len(blds) * test_frac)), replace=False).tolist())
    digest = hashlib.sha256(",".join(test).encode()).hexdigest()
    return {"name": name, "test_buildings": test, "sha256": digest, "n_buildings": len(blds)}


def load(name: str = "world_v1") -> list[dict]:
    files = sorted((CACHE / name).glob("*.pkl"))
    out = []
    for f in files:
        with open(f, "rb") as fh:
            out.append(pickle.load(fh))
    return out


def load_split(name: str = "world_v1") -> dict:
    s = json.loads((ROOT / "data" / "synthetic" / f"{name}_split.json").read_text())
    assert hashlib.sha256(",".join(s["test_buildings"]).encode()).hexdigest() == s["sha256"], "test split altered"
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="world_v1")
    ap.add_argument("--buildings", type=int, default=160)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--days", type=int, default=21)
    a = ap.parse_args()
    units = generate_world(a.seed, a.buildings)
    jobs = [(a.name, a.seed, a.buildings, i, a.days) for i in range(len(units))]
    pmap(_build, jobs)
    sp_path = ROOT / "data" / "synthetic" / f"{a.name}_split.json"
    if sp_path.exists():
        s = load_split(a.name)  # frozen: never regenerate
        print("split frozen:", s["sha256"][:12])
    else:
        s = split(a.name, [u.building_id for u in units], a.seed)
        s.update({"seed": a.seed, "buildings": a.buildings, "days": a.days, "n_units": len(units)})
        sp_path.write_text(json.dumps(s, indent=1))
        print("froze split", s["sha256"][:12])
    print(len(units), "units")


if __name__ == "__main__":
    main()
