"""Real-data ingestion CLI (all inputs/outputs under git-ignored data/private/ unless aggregated).

  python -m ingest.cli colocation             # per-kit offsets from data/private/raw/colocation/<kit>/*.log
  python -m ingest.cli unit --unit U03        # targets for one unit from data/private/raw/U03/<kit>/*.log

Private inputs:
  data/private/kits.csv      kit_id,unit_pid,room,installed_utc,removed_utc,placement_notes
  data/private/units.csv     unit_pid,address,unit_number,floor,... (+ lat,lon after geocoding)
  data/private/diary/<unit>.csv   time_local,room,event   (event: OPEN|CLOSED|BLINDS_DOWN|BLINDS_UP|AC_ON|AC_OFF)
Outputs:
  data/private/calibration.json                 per-kit offsets (private: tied to kit IDs only, but kept local)
  data/private/targets/<unit>.pkl               per-room daily/nightly targets
  results/m1/colocation_<date>.json             inter-kit agreement (aggregate; no location data)
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from core.provenance import REPO, hash_paths, write_result
from ingest.logs import Calibration, KitLog, clean_minute, colocation_calibration, parse_files
from ingest.targets import TZ, daily_heat, daily_sun_hours, nightly_noise, window_open_nights

PRIVATE = REPO / "data" / "private"


def retime(log: KitLog, installed_utc: str | None) -> pd.DataFrame:
    """Kits without NTP log seconds-since-boot (flag 0x01). Shift such rows so that the first sample equals
    the human-recorded install time (uncertainty = how precisely the install time was noted)."""
    m = log.minute.copy()
    if m.empty or "flags" not in m:
        return m
    nontp = (m["flags"].astype(int) & 0x01) > 0
    if nontp.all() and installed_utc:
        shift = pd.Timestamp(installed_utc, tz="UTC") - m.index[0]
        m.index = m.index + shift
        m["flags"] = m["flags"].astype(int) & ~0x01
    return m


def cmd_colocation(_: argparse.Namespace) -> int:
    root = PRIVATE / "raw" / "colocation"
    if not root.exists():
        print("no co-location data yet (data/private/raw/colocation/<kit>/*.log) — see HUMAN_TODO §4")
        return 0
    kits = {}
    for kdir in sorted(p for p in root.iterdir() if p.is_dir()):
        log = parse_files(sorted(kdir.glob("*.log")))
        kits[kdir.name] = clean_minute(log.minute)
    cal, report = colocation_calibration(kits)
    floors = {k: float(np.nanpercentile(d["laeq"], 1)) for k, d in kits.items() if "laeq" in d}
    (PRIVATE / "calibration.json").write_text(
        json.dumps(
            {
                "temp_offset": cal.temp_offset,
                "db_offset": cal.db_offset,
                "lux_scale": cal.lux_scale,
                "mic_floor": floors,
            },
            indent=1,
        )
    )
    date = min(d.index.min() for d in kits.values()).strftime("%Y%m%d")
    write_result(
        f"m1/colocation_{date}.json",
        {
            "n_kits": len(kits),
            "agreement": report,
            "mic_floor_db": {
                "median": float(np.median(list(floors.values()))),
                "max": float(np.max(list(floors.values()))),
            },
        },
        seed=None,
        config={},
        data_hash=hash_paths([root]),
        data_kind="real-sensor",
    )
    print("calibration written for", len(kits), "kits")
    return 0


def load_calibration() -> tuple[Calibration, dict]:
    p = PRIVATE / "calibration.json"
    if not p.exists():
        return Calibration(), {}
    d = json.loads(p.read_text())
    return Calibration(d["temp_offset"], d["db_offset"], d["lux_scale"]), d.get("mic_floor", {})


def diary_open_nights(unit: str) -> dict[str, set]:
    """Nights (evening date) with the window opened in each room according to the diary."""
    p = PRIVATE / "diary" / f"{unit}.csv"
    out: dict[str, set] = {}
    if not p.exists():
        return out
    d = pd.read_csv(p)
    d["t"] = pd.to_datetime(d["time_local"]).dt.tz_localize(TZ)
    for room, g in d.sort_values("t").groupby("room"):
        state, since = False, None
        nights: set = set()
        for _, r in g.iterrows():
            if r["event"] == "OPEN":
                state, since = True, r["t"]
            elif r["event"] == "CLOSED" and state:
                for t in pd.date_range(since, r["t"], freq="30min"):
                    if t.hour >= 23 or t.hour < 7:
                        nights.add((t - pd.Timedelta(hours=12)).date())
                state = False
        out[room] = nights
    return out


def cmd_unit(a: argparse.Namespace) -> int:
    kits_p, units_p = PRIVATE / "kits.csv", PRIVATE / "units.csv"
    if not kits_p.exists() or not units_p.exists():
        print("missing data/private/kits.csv or units.csv — see HUMAN_TODO §3/§6")
        return 1
    kits = pd.read_csv(kits_p)
    units = pd.read_csv(units_p)
    urow = units[units["unit_pid"] == a.unit].iloc[0]
    lat, lon = float(urow["lat"]), float(urow["lon"])
    cal, floors = load_calibration()
    from bench.common import weather

    out = {}
    diary = diary_open_nights(a.unit)
    for _, k in kits[kits["unit_pid"] == a.unit].iterrows():
        files = sorted((PRIVATE / "raw" / a.unit / str(k["kit_id"])).glob("*.log"))
        if not files:
            continue
        log = parse_files(files)
        m = retime(log, k.get("installed_utc"))
        d = cal.apply(str(k["kit_id"]), clean_minute(m))
        lo, hi = pd.Timestamp(k["installed_utc"], tz="UTC"), pd.Timestamp(k["removed_utc"], tz="UTC")
        d = d[(d.index >= lo + pd.Timedelta(hours=2)) & (d.index <= hi - pd.Timedelta(hours=1))]
        noise = nightly_noise(d)
        if len(noise):
            try:
                noise["open_heur"] = (
                    window_open_nights(d, weather()["temp_c"], noise).reindex(noise.index).fillna(False)
                )
            except Exception:
                noise["open_heur"] = False
            noise["open_diary"] = [n in diary.get(k["room"], set()) for n in noise.index]
            noise["has_diary"] = bool(diary)
        out[k["room"]] = {
            "kit": str(k["kit_id"]),
            "sun": daily_sun_hours(d, lat, lon),
            "noise": noise,
            "heat": daily_heat(d),
            "mic_floor": floors.get(str(k["kit_id"])),
            "start": str(d.index.min()),
            "end": str(d.index.max()),
        }
    path = PRIVATE / "targets" / f"{a.unit}.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(out, f)
    print(a.unit, {r: {k: len(v[k]) for k in ("sun", "noise", "heat")} for r, v in out.items()})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("colocation")
    u = sub.add_parser("unit")
    u.add_argument("--unit", required=True)
    a = ap.parse_args()
    return {"colocation": cmd_colocation, "unit": cmd_unit}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())


_ = Path
