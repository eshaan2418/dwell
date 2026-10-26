"""De-identified dataset release (M12).

Per-room aggregated targets + coarse location features + scan-derived geometry summaries. Real units are
included ONLY with consent code R (data/private/consent_scope.csv: unit_pid,codes) and only as:
neighbourhood-free coarse location = orientation (N/E/S/W), floor band, building-age band, street class;
never addresses, coordinates, raw logs, video, or exact geometry. Synthetic units are released in full
aggregate form (they are not people's homes).

Output: release/dwell_rooms_<kind>.csv + release/DATASHEET.md (copied from docs/DATASHEET.md).
"""

from __future__ import annotations

import shutil

import numpy as np
import pandas as pd

from bench.synth_dataset import load, load_split
from core.provenance import REPO, hash_paths, write_result
from core.scene import Unit
from hybrid.features import group_labels

OUT = REPO / "release"


def synthetic_rows() -> pd.DataFrame:
    test_b = set(load_split()["test_buildings"])
    rows = []
    for r in load():
        u = Unit.from_dict(r["obs"])
        for rid, t in r["targets"].items():
            g = group_labels(u, rid)
            n = t["noise"]
            rows.append(
                {
                    "room_pid": rid,
                    "split": "test" if u.building_id in test_b else "train",
                    "room_kind": u.room(rid).kind,
                    "orientation": g["g_orient"],
                    "floor_band": g["g_floor"],
                    "age_band": g["g_era"],
                    "building_kind": u.building_kind,
                    "street_class": u.meta.get("street_class"),
                    "season_start_month": int(r["start"].month),
                    "n_days": int(r["days"]),
                    "sun_h_day_mean": float(t["sun"]["sun_h"].mean()) if len(t["sun"]) else np.nan,
                    "night_laeq_mean_db": float(n["laeq"].mean()) if len(n) else np.nan,
                    "night_la90_mean_db": float(n["la90"].mean()) if len(n) else np.nan,
                    "frac_minutes_at_mic_floor": float(n["floor_frac"].mean()) if len(n) else np.nan,
                    "daily_peak_temp_mean_c": float(t["heat"]["peak"].mean()) if len(t["heat"]) else np.nan,
                    "window_area_m2": float(sum(w.width * w.height for w in u.windows_of(rid))),
                }
            )
    return pd.DataFrame(rows)


def real_rows() -> pd.DataFrame:
    scope = REPO / "data" / "private" / "consent_scope.csv"
    if not scope.exists():
        return pd.DataFrame()
    s = pd.read_csv(scope)
    ok = set(s.loc[s["codes"].astype(str).str.contains("R"), "unit_pid"])
    rows = []
    import pickle

    for pid in sorted(ok):
        tp = REPO / "data" / "private" / "targets" / f"{pid}.pkl"
        up = REPO / "data" / "private" / "units" / pid / "unit.json"
        if not tp.exists() or not up.exists():
            continue
        u = Unit.load(up)
        tg = pickle.loads(tp.read_bytes())
        for room, t in tg.items():
            rid = f"{pid}_{room}"
            g = group_labels(u, rid)
            rows.append(
                {
                    "room_pid": f"{pid}_{room}",
                    "room_kind": room,
                    "orientation": g["g_orient"],
                    "floor_band": g["g_floor"],
                    "age_band": g["g_era"],
                    "building_kind": u.building_kind,
                    "season_start_month": pd.Timestamp(t["start"]).month,
                    "sun_h_day_mean": float(t["sun"]["sun_h"].mean()) if len(t["sun"]) else np.nan,
                    "night_laeq_mean_db": float(t["noise"]["laeq"].mean()) if len(t["noise"]) else np.nan,
                    "daily_peak_temp_mean_c": float(t["heat"]["peak"].mean()) if len(t["heat"]) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    syn = synthetic_rows()
    syn.to_csv(OUT / "dwell_rooms_synthetic.csv", index=False)
    real = real_rows()
    if len(real):
        real.to_csv(OUT / "dwell_rooms_real.csv", index=False)
    shutil.copy(REPO / "docs" / "DATASHEET.md", OUT / "DATASHEET.md")
    write_result(
        "m12/release.json",
        {
            "n_synthetic_rooms": len(syn),
            "n_real_rooms": len(real),
            "real_status": "released" if len(real) else "awaiting-human (no consented units)",
        },
        seed=7,
        config={},
        data_hash=hash_paths([OUT / "dwell_rooms_synthetic.csv"]),
        data_kind="synthetic",
    )
    print(len(syn), "synthetic rooms;", len(real), "real rooms")


if __name__ == "__main__":
    main()
