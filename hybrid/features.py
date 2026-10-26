"""Tabular datasets (one row per room-day / room-night) joining targets, physics outputs and features.

Feature families (for ablations):
  physics   physics ensemble outputs (only for physics-based methods)
  geometry  scan-derived geometry (window size/orientation, room size, floor, overhang)
  meta      building metadata (kind, year, levels) and visual cues
  geo       public geodata summaries (road class/AADT/distance, transit, neighbour heights)
  weather   weather over the target day (sunshine, temperature)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from core.scene import Unit
from physics.sun.daylight import sensor_window
from synth.priors import era_of

TZ = "America/Toronto"
KIND_CODE = {"house": 0, "lowrise": 1, "midrise": 2, "highrise": 3}
CLASS_CODE = {"service": 0, "residential": 1, "tertiary": 2, "secondary": 3, "primary": 4, "trunk": 5, "motorway": 6}
FAMILIES = ("physics", "geometry", "meta", "geo", "weather")


def _geo_features(u: Unit, rid: str) -> dict[str, float]:
    walls = u.walls_of(rid)
    wl = walls[0]
    p = Point(wl.cx, wl.cy)
    d_road, cls, aadt = 999.0, 0, 0.0
    for r in u.roads:
        d = LineString(r.coords).distance(p)
        if d < d_road:
            d_road, cls, aadt = d, CLASS_CODE.get(r.road_class, 1), float(r.aadt or 0.0)
    d_tr = min((LineString(t.coords).distance(p) for t in u.transit), default=999.0)
    az = np.radians(wl.azimuth)
    front = Point(wl.cx + 30 * np.sin(az), wl.cy + 30 * np.cos(az)).buffer(30)
    hs = [b.height for b in u.context_buildings if b.id != u.building_id and Polygon(b.footprint).intersects(front)]
    return {
        "geo_road_dist": float(d_road),
        "geo_road_class": float(cls),
        "geo_road_aadt": aadt,
        "geo_transit_dist": float(d_tr),
        "geo_front_bldg_h": float(np.mean(hs)) if hs else 0.0,
        "geo_n_trees": float(len(u.trees)),
    }


def _static_features(u: Unit, rid: str) -> dict[str, float]:
    room = u.room(rid)
    sw = sensor_window(u, rid)
    wins = u.windows_of(rid)
    area = Polygon(room.polygon).area
    cues = (sw.cues if sw else {}) or {}
    uc = u.meta.get("cues", {})
    year = u.year_built if u.year_built is not None else np.nan
    f = {
        "geom_az_sin": float(np.sin(np.radians(sw.azimuth))) if sw else 0.0,
        "geom_az_cos": float(np.cos(np.radians(sw.azimuth))) if sw else 0.0,
        "geom_win_area": float(sum(w.width * w.height for w in wins)),
        "geom_wwr": float(sum(w.width * w.height for w in wins) / max(area, 1)),
        "geom_floor_area": float(area),
        "geom_floor": float(u.floor),
        "geom_overhang": float(max((w.overhang_depth for w in wins), default=0.0)),
        "geom_reveal": float(sw.reveal_depth) if sw else 0.0,
        "geom_bedroom": float(room.kind == "bedroom"),
        "geom_has_blinds": float(bool(sw and sw.has_blinds)),
        "meta_kind": float(KIND_CODE.get(u.building_kind or "lowrise", 1)),
        "meta_year": float(year),
        "meta_levels": float(u.meta.get("levels", np.nan)),
        "meta_top": float(bool(u.meta.get("top_floor"))),
        "meta_has_ac": float(u.has_ac),
        "meta_pane_obs": float(cues.get("pane_count_obs") or np.nan),
        "meta_tint": float(bool(cues.get("lowe_tint_obs"))),
        "meta_draft": float(bool(cues.get("draft_cue_obs"))),
        "meta_radiator": float(bool(uc.get("radiator_visible"))),
        "meta_wall_thick": float(uc.get("wall_thickness_obs", np.nan)),
    }
    f.update(_geo_features(u, rid))
    return f


def group_labels(u: Unit, rid: str) -> dict[str, str]:
    sw = sensor_window(u, rid)
    az = sw.azimuth if sw else 0.0
    orient = ["N", "E", "S", "W"][int(((az + 45) % 360) // 90)]
    fb = "0-2" if u.floor <= 2 else ("3-9" if u.floor <= 9 else "10+")
    era = era_of(u.year_built) if u.year_built is not None else "unknown"
    return {"g_orient": orient, "g_floor": fb, "g_era": era}


def daily_weather(weather: pd.DataFrame) -> pd.DataFrame:
    loc = weather.copy()
    loc.index = loc.index.tz_convert(TZ)
    with np.errstate(divide="ignore", invalid="ignore"):
        sf = np.clip(loc["dni"] / loc["dni_clear"], 0, 1).where(loc["dni_clear"] > 5)
    g = loc.groupby(loc.index.date)
    return pd.DataFrame(
        {
            "wx_tmax": g["temp_c"].max(),
            "wx_tmean": g["temp_c"].mean(),
            "wx_sunfrac": sf.groupby(loc.index.date).mean(),
            "wx_ghi": g["ghi"].mean(),
        }
    )


def build_tables(
    records: list[dict], preds: dict[str, dict], weather: pd.DataFrame, test_buildings: set[str]
) -> dict[str, pd.DataFrame]:
    wd = daily_weather(weather)
    sun_rows, noise_rows, heat_rows = [], [], []
    for rec in records:
        u = Unit.from_dict(rec["obs"])
        uid, bid = u.id, u.building_id
        p = preds[uid]
        split = "test" if bid in test_buildings else "train"
        for rid, tg in rec["targets"].items():
            base = {
                "unit": uid,
                "building": bid,
                "room": rid,
                "split": split,
                **_static_features(u, rid),
                **group_labels(u, rid),
            }
            # ---- sun (room-day)
            ps = p["sun"].get(rid)
            if ps is not None:
                for day, row in tg["sun"].iterrows():
                    if day not in ps.index:
                        continue
                    q = ps.loc[day]
                    w = wd.loc[day] if day in wd.index else pd.Series(dtype=float)
                    sun_rows.append(
                        {
                            **base,
                            "day": day,
                            "y": row["sun_h"],
                            "y_true_world": row["sun_h_true"],
                            "phys_nominal": q["physics"],
                            "phys_mc_mean": q["mc_mean"],
                            "phys_mc_std": q["mc_std"],
                            "base_sunpath_only": q["sunpath_only"],
                            "wx_sunfrac": w.get("wx_sunfrac", np.nan),
                            "wx_doy_sin": np.sin(2 * np.pi * pd.Timestamp(day).dayofyear / 365.25),
                            "wx_doy_cos": np.cos(2 * np.pi * pd.Timestamp(day).dayofyear / 365.25),
                        }
                    )
            # ---- noise (room-night), closed nights by heuristic (diary unavailable in synthetic)
            pn = p["noise"].get(rid)
            nz = tg["noise"]
            if pn is not None and len(nz):
                for day, row in nz.iterrows():
                    noise_rows.append(
                        {
                            **base,
                            "day": day,
                            "y": row["laeq"],
                            "y_la90": row["la90"],
                            "y_trim": row["laeq_trim"],
                            "floor_frac": row["floor_frac"],
                            "open_heur": bool(row["open_heur"]),
                            "open_true": bool(row["open_true"]),
                            "phys_default": pn["physics_default"],
                            "phys_mc_mean": pn["mc_mean"],
                            "phys_mc_std": pn["mc_std"],
                            "phys_raw_mean": pn["mc_raw_mean"],
                            "phys_raw_std": pn["mc_raw_std"],
                            "phys_outdoor": pn["outdoor_night"],
                            "phys_floor": pn["floor"],
                            "base_noisemap_only": pn["noisemap_only"],
                            "phys_attr_road": pn["attribution_db"].get("road", -99.0),
                            "phys_attr_transit": max(
                                [v for k, v in pn["attribution_db"].items() if k != "road"], default=-99.0
                            ),
                            "wx_doy_sin": np.sin(2 * np.pi * pd.Timestamp(day).dayofyear / 365.25),
                            "wx_doy_cos": np.cos(2 * np.pi * pd.Timestamp(day).dayofyear / 365.25),
                            "wx_tmean": wd.loc[day, "wx_tmean"] if day in wd.index else np.nan,
                        }
                    )
            # ---- heat (room-day)
            ph = p["heat"].get(rid)
            if ph is not None:
                omax = p["heat"]["_outdoor_max"]
                for day, row in tg["heat"].iterrows():
                    if day not in ph.index:
                        continue
                    q = ph.loc[day]
                    heat_rows.append(
                        {
                            **base,
                            "day": day,
                            "y": row["peak"],
                            "phys_default": q["physics_default"],
                            "phys_mc_mean": q["mc_mean"],
                            "phys_mc_std": q["mc_std"],
                            "base_outdoor_max": float(omax.get(day, np.nan)),
                            "wx_tmax": wd.loc[day, "wx_tmax"] if day in wd.index else np.nan,
                            "wx_tmean": wd.loc[day, "wx_tmean"] if day in wd.index else np.nan,
                            "wx_ghi": wd.loc[day, "wx_ghi"] if day in wd.index else np.nan,
                            "wx_doy_sin": np.sin(2 * np.pi * pd.Timestamp(day).dayofyear / 365.25),
                            "wx_doy_cos": np.cos(2 * np.pi * pd.Timestamp(day).dayofyear / 365.25),
                        }
                    )
    return {"sun": pd.DataFrame(sun_rows), "noise": pd.DataFrame(noise_rows), "heat": pd.DataFrame(heat_rows)}


def feature_columns(df: pd.DataFrame, families: tuple[str, ...]) -> list[str]:
    pref = {"physics": "phys_", "geometry": "geom_", "meta": "meta_", "geo": "geo_", "weather": "wx_"}
    return [c for c in df.columns if any(c.startswith(pref[f]) for f in families)]
