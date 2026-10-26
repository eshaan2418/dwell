"""Real-sensor validation (M5-M7 real rows). Runs only when consented real units exist.

For each real unit: observed geometry (data/private/units/<pid>/floorplan.yaml via recon/manual.py, or a
reconstruction unit.json), predictions over the deployment period with ECCC/NASA POWER weather, and the
same metric harness as synthetic. Intervals for real data are recalibrated by leave-one-building-out
conformal on real residuals of the (synthetic-trained) hybrid model. Writes results/real/validation.json
with data_kind "real-sensor"; if there is no real data it records status `awaiting-human`.
"""

from __future__ import annotations

import pickle
import sys

import numpy as np
import pandas as pd

from core.provenance import REPO, hash_paths, write_result

PRIVATE = REPO / "data" / "private"


def main() -> int:
    tdir = PRIVATE / "targets"
    units = sorted(p.stem for p in tdir.glob("*.pkl")) if tdir.exists() else []
    if not units:
        write_result(
            "real/validation.json",
            {
                "status": "awaiting-human",
                "n_units": 0,
                "reason": "no consented real units with sensor data yet (HUMAN_TODO)",
            },
            seed=None,
            config={},
            data_hash="none",
            data_kind="none",
        )
        print("no real units yet — wrote awaiting-human status")
        return 0
    from bench.common import weather
    from bench.train_models import OUT as MODELS
    from hybrid.evaluate import metrics
    from hybrid.features import build_tables
    from hybrid.models import DwellModels
    from hybrid.physics_predict import PredictOptions, predict_all
    from recon.manual import unit_from_yaml

    models = DwellModels.load(MODELS)
    recs, preds = [], {}
    for pid in units:
        with open(tdir / f"{pid}.pkl", "rb") as f:
            tg = pickle.load(f)
        unit = unit_from_yaml(PRIVATE / "units" / pid / "floorplan.yaml")
        rooms = {f"{pid}_{k}": v for k, v in tg.items()}
        start = pd.Timestamp(min(v["start"] for v in rooms.values())).tz_convert("America/Toronto").normalize()
        end = pd.Timestamp(max(v["end"] for v in rooms.values())).tz_convert("America/Toronto")
        days = int((end - start).days) + 1
        floor = {rid: float(v.get("mic_floor") or 33.0) for rid, v in rooms.items()}
        preds[unit.id] = predict_all(
            unit, models.hidden.posterior(unit), start, days, weather(), seed=0, o=PredictOptions(), kit_floor=floor
        )
        for v in rooms.values():
            if len(v["noise"]):
                v["noise"]["open_true"] = v["noise"].get("open_diary", False)
            v["sun"]["sun_h_true"] = np.nan
        recs.append({"obs": unit.to_dict(), "targets": rooms})
    tabs = build_tables(recs, preds, weather(), set())
    out = {"n_units": len(units)}
    for target, tm in models.targets.items():
        df = tabs[target].dropna(subset=["y"]).copy()
        if target == "noise":
            closed = ~df["open_true"] if df.get("open_true") is not None and df["open_true"].any() else ~df["open_heur"]
            df = df[closed]
        if df.empty:
            continue
        df["hybrid_synth"] = tm.predict(df)
        res = {}
        for name, col in [
            ("physics_default", "phys_nominal" if target == "sun" else "phys_default"),
            ("physics_inferred", "phys_mc_mean"),
            ("hybrid_synthetic_trained", "hybrid_synth"),
        ]:
            rows = []
            for b in df["building"].unique():  # LOBO conformal recalibration on real residuals
                cal = df[df.building != b]
                te = df[df.building == b]
                half = (
                    np.quantile(np.abs(cal["y"] - cal[col]), min(0.9 * (1 + 1 / max(cal.building.nunique(), 1)), 1))
                    if len(cal)
                    else np.nan
                )
                rows.append(te.assign(pred=te[col], lo=te[col] - half, hi=te[col] + half))
            res[name] = metrics(pd.concat(rows))
        out[target] = res
    seasons = sorted({pd.Timestamp(d).strftime("%Y-%m") for t in tabs.values() for d in t.get("day", [])})
    out["season_coverage_months"] = seasons
    write_result(
        "real/validation.json",
        out,
        seed=0,
        config={"units": len(units)},
        data_hash=hash_paths([tdir]),
        data_kind="real-sensor",
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
