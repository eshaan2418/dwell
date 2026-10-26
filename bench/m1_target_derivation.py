"""M1: calibrate and validate the lux->direct-sun rule and the open-window heuristic on synthetic units.

Calibration units (seed 101) choose THETA/LUX_MIN by grid search; validation units (seed 202) report
the error of sensor-derived targets vs the simulator's true sensor-point sun, i.e. *target noise*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bench.common import pmap, weather
from core.provenance import hash_paths, write_result
from ingest.targets import TZ, night_features, nightly_noise, sun_minutes
from synth.generator import generate_world
from synth.truth import Deployment, simulate_unit

THETAS = [0.35, 0.45, 0.55, 0.65, 0.75]
LUXMINS = [2500.0, 4000.0, 6000.0, 8000.0]


def _one(args: tuple[int, int, str]) -> dict:
    seed, idx, start = args
    units = generate_world(seed, 40)
    u = units[idx]
    rng = np.random.default_rng(seed * 1000 + idx)
    out = simulate_unit(rng, u, weather(), Deployment(pd.Timestamp(start, tz=TZ), 10))
    res = {"unit": u.id, "start": start, "rooms": {}}
    for rid, d in out["rooms"].items():
        tr = out["truth"][rid]["true_sensor_sun_min"]
        tl = tr.copy()
        tl.index = tl.index.tz_convert(TZ)
        true_h = tl.groupby(tl.index.date).sum() / 60.0
        grid = {}
        for th in THETAS:
            for lm in LUXMINS:
                s = sun_minutes(d, u.lat, u.lon, theta=th, lux_min=lm)
                sl = s.copy()
                sl.index = sl.index.tz_convert(TZ)
                est = sl.groupby(sl.index.date).sum() / 60.0
                grid[f"{th}_{lm}"] = (est - true_h).abs().mean()
        noise = nightly_noise(d)
        outdoor = weather()["temp_c"]
        feats = night_features(d, outdoor, noise) if len(noise) else pd.DataFrame()
        om = out["truth"][rid]["open_window_minutes"]
        ol = om.copy()
        ol.index = (ol.index.tz_convert(TZ) - pd.Timedelta(hours=12)).normalize().date
        true_open = ol.groupby(level=0).max().astype(bool)
        both = feats.index.intersection(true_open.index)
        res["rooms"][rid] = {
            "grid": grid,
            "true_mean_h": float(true_h.mean()),
            "nights": [{**feats.loc[k].to_dict(), "open": bool(true_open[k])} for k in both],
        }
    return res


def jobs(seed: int, n: int) -> list[tuple[int, int, str]]:
    """Half the deployments start in Jun-Aug (warm nights exercise the open-window heuristic)."""
    rng = np.random.default_rng(seed)
    starts = pd.date_range("2025-01-05", "2025-12-15", freq="7D")
    summer = pd.date_range("2025-06-01", "2025-08-20", freq="5D")
    return [
        (seed, i, str((summer if i % 2 else starts)[rng.integers(len(summer if i % 2 else starts))].date()))
        for i in range(n)
    ]


def summarise(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        for rid, v in r["rooms"].items():
            rows.append({"room": rid, **v["grid"]})
    return pd.DataFrame(rows).set_index("room")


def main() -> None:
    cal = pmap(_one, jobs(101, 30))
    val = pmap(_one, jobs(202, 30))
    gcal = summarise(cal).mean()
    best = gcal.idxmin()
    th, lm = best.split("_")
    gval = summarise(val)
    per_room_err = gval[best]

    def nights(res: list[dict]) -> pd.DataFrame:
        return pd.DataFrame([n for r in res for v in r["rooms"].values() for n in v["nights"]]).fillna(
            {"slope": 0.0, "dt_io": 0.0}
        )

    def confusion(df: pd.DataFrame, st: float, dt: float, lt: float) -> dict:
        p = ((df.slope < st) & (df.dt_io > dt)) | (df.loud > lt)
        t = df.open
        tp, fp = int((p & t).sum()), int((p & ~t).sum())
        fn, tn = int((~p & t).sum()), int((~p & ~t).sum())
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        return {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": tp / max(tp + fp, 1),
            "recall": tp / max(tp + fn, 1),
            "f1": f1,
        }

    ncal, nval = nights(cal), nights(val)
    cands = [
        (st, dt, lt)
        for st in [-0.1, -0.15, -0.2, -0.25, -0.35]
        for dt in [0.0, 1.0, 2.0, 3.0]
        for lt in [3.0, 4.0, 6.0, 8.0, 99.0]
    ]
    st, dt, lt = max(cands, key=lambda c: confusion(ncal, *c)["f1"])
    open_val = {
        **confusion(nval, st, dt, lt),
        "thresholds": {"slope": st, "dt_io": dt, "loud": lt},
        "n_nights": int(len(nval)),
        "n_open": int(nval.open.sum()),
    }
    rng = np.random.default_rng(0)
    boots = [float(np.mean(rng.choice(per_room_err.to_numpy(), len(per_room_err)))) for _ in range(2000)]
    write_result(
        "m1/target_derivation.json",
        {
            "chosen": {"theta": float(th), "lux_min": float(lm)},
            "calibration_grid_mean_abs_err_h": {k: float(v) for k, v in gcal.items()},
            "validation": {
                "n_rooms": int(len(per_room_err)),
                "daily_sun_hours_abs_err_mean_h": float(per_room_err.mean()),
                "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                "grid_mean_abs_err_h": {k: float(v) for k, v in gval.mean().items()},
            },
            "open_window_heuristic_validation": open_val,
            "note": "Target noise of sensor-derived sun hours vs simulator truth (synthetic sensor model).",
        },
        seed=101,
        config={"thetas": THETAS, "luxmins": LUXMINS, "n_cal": 30, "n_val": 30, "days": 10},
        data_hash=hash_paths(["data/weather/toronto_hourly_2016_2025.csv.gz", "synth"]),
        data_kind="synthetic",
    )
    print("best", best, "val err", per_room_err.mean(), "open", open_val)


if __name__ == "__main__":
    main()
