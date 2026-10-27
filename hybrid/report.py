"""Generate a `dwell-report/1` bundle (docs/REPORT_SCHEMA.md) for an observed unit.

Interval kinds (recorded per value):
  conformal_room   cross-conformal (10-fold, building-grouped) on room-mean residuals of the hybrid model
  conformal_row    same on single-day residuals (single-day quantities, e.g. heat-wave peak)
  physics_ensemble 5-95 % of the physics Monte Carlo ensemble (not empirically calibrated: indoor intrusive
                   noise cannot be measured below the sensor's self-noise floor)
Calibration data are the synthetic world (until real units exist) — the report says so.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from core.provenance import git_commit
from core.scene import FRAME_TYPES, GLAZING_TYPES, WALL_TYPES, Unit
from hybrid.auralize import synthesize, write_wav
from hybrid.features import _static_features, daily_weather, group_labels
from hybrid.models import DwellModels
from hybrid.physics_predict import PredictOptions, predict_heat, predict_noise, predict_sun
from hybrid.unit_sobol import HEAT_PARAMS, NOISE_PARAMS, room_sobol
from physics.acoustics.model import (
    AADT_BY_CLASS,
    HOURLY_TRAFFIC_PROFILE,
    NIGHT_HOURS,
    NoiseParams,
    predict_room_noise,
)
from physics.sun.daylight import average_daylight_factor, sun_patch_polygon, window_contexts, window_frame
from physics.sun.solar import solar_position

TZ = "America/Toronto"
DISCLAIMER = (
    "Dwell estimates what it is like to live here (sun, night noise, summer heat) from a short video and "
    "public data. These are predictions with uncertainty ranges, not measurements, and not a building "
    "inspection, mould/structural assessment or legal disclosure."
)
WHO_NOTE = (
    "WHO (2018) Environmental Noise Guidelines set OUTDOOR night-time road-traffic exposure targets (Lnight); "
    "indoor levels here are not directly comparable."
)


def reference_periods(weather: pd.DataFrame) -> dict[str, Any]:
    """Typical year = year closest to the decade medians of JJA mean temperature and annual sunshine fraction.
    Heat wave = the 5-day window with the highest mean daily maximum temperature in the record."""
    loc = weather.copy()
    loc.index = loc.index.tz_convert(TZ)
    with np.errstate(divide="ignore", invalid="ignore"):
        sf = np.clip(loc["dni"] / loc["dni_clear"], 0, 1).where(loc["dni_clear"] > 5)
    years = sorted(set(loc.index.year))
    rows = []
    for y in years:
        d = loc[loc.index.year == y]
        jja = d[d.index.month.isin([6, 7, 8])]["temp_c"].mean()
        rows.append((y, jja, sf[sf.index.year == y].mean()))
    df = pd.DataFrame(rows, columns=["year", "jja", "sun"]).dropna()
    z = ((df[["jja", "sun"]] - df[["jja", "sun"]].median()) / df[["jja", "sun"]].std()).abs().sum(axis=1)
    typ = int(df.loc[z.idxmin(), "year"])
    tmax = loc["temp_c"].resample("D").max()
    roll = tmax.rolling(5).mean()
    end = roll.idxmax()
    hw_start = (end - pd.Timedelta(days=4)).normalize()
    return {
        "typical_year": typ,
        "heatwave_start": hw_start,
        "heatwave_days": 5,
        "heatwave_mean_tmax": float(roll.max()),
    }


def _iv(pred: float, half: float, kind: str) -> dict[str, Any]:
    return {
        "pred": round(float(pred), 2),
        "lo": round(float(pred - half), 2),
        "hi": round(float(pred + half), 2),
        "interval_kind": kind,
    }


def _rows(unit: Unit, rid: str, extra: pd.DataFrame) -> pd.DataFrame:
    base = {**_static_features(unit, rid), **group_labels(unit, rid)}
    return pd.DataFrame([{**base, **r} for r in extra.to_dict("records")], index=extra.index)


def _doy(days: pd.Index) -> tuple[np.ndarray, np.ndarray]:
    doy = np.array([pd.Timestamp(d).dayofyear for d in days])
    return np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)


def _geometry(unit: Unit, radius: float = 150.0) -> dict[str, Any]:
    cx = float(np.mean([w.cx for w in unit.windows]))
    cy = float(np.mean([w.cy for w in unit.windows]))
    c = Point(cx, cy)
    wins = []
    for w in unit.windows:
        g, _, t = window_frame(w)
        corners = [
            g + t * u + np.array([0, 0, v])
            for u, v in [(-w.width / 2, 0), (w.width / 2, 0), (w.width / 2, w.height), (-w.width / 2, w.height)]
        ]
        wins.append(
            {
                "id": w.id,
                "room_id": w.room_id,
                "corners": [[round(float(x), 3) for x in p] for p in corners],
                "azimuth": round(w.azimuth, 1),
                "overhang_depth": round(w.overhang_depth, 2),
            }
        )
    blds = [
        {
            "footprint": [[round(x, 2), round(y, 2)] for x, y in b.footprint],
            "height": round(b.height, 2),
            "own": b.id == unit.building_id,
        }
        for b in unit.context_buildings
        if Polygon(b.footprint).distance(c) < radius
    ]
    roads = []
    for r in unit.roads:
        from shapely.geometry import LineString

        seg = LineString(r.coords).intersection(c.buffer(radius * 1.5))
        if seg.is_empty:
            continue
        parts = [seg] if seg.geom_type == "LineString" else list(getattr(seg, "geoms", []))
        for p in parts:
            roads.append({"coords": [[round(x, 2), round(y, 2)] for x, y in p.coords], "road_class": r.road_class})
    names = {"bedroom": "Bedroom", "living": "Living room", "kitchen": "Kitchen"}
    rooms = [
        {
            "id": r.id,
            "kind": r.kind,
            "name": names.get(r.kind, r.kind.title()),
            "polygon": [[round(x, 3), round(y, 3)] for x, y in r.polygon],
            "floor_z": round(r.floor_z, 3),
            "ceiling_height": round(r.ceiling_height, 3),
        }
        for r in unit.rooms
    ]
    trees = [
        {"x": round(t.x, 2), "y": round(t.y, 2), "radius": round(t.radius, 2), "height": round(t.height, 2)}
        for t in unit.trees
        if Point(t.x, t.y).distance(c) < radius
    ]
    return {"rooms": rooms, "windows": wins, "context_buildings": blds, "roads": roads, "trees": trees}


def _sun_viewer(unit: Unit, year: int) -> dict[str, Any]:
    dates = [f"{year}-12-21", f"{year}-03-20", f"{year}-06-21", f"{year}-09-22"]
    hours = [h / 2 for h in range(12, 41)]
    pos: list[list[list[float]]] = []
    patches: dict[str, list[list[Any]]] = {r.id: [] for r in unit.rooms}
    for d in dates:
        times = pd.DatetimeIndex([pd.Timestamp(d, tz=TZ) + pd.Timedelta(hours=h) for h in hours])
        sp = solar_position(times, unit.lat, unit.lon)
        pos.append(
            [[round(float(a), 2), round(float(e), 2)] for a, e in zip(sp["azimuth"], sp["elevation"], strict=True)]
        )
        ctxs = {c.window.id: c for c in window_contexts(unit)}
        for r in unit.rooms:
            row: list[Any] = []
            for a, e in zip(sp["azimuth"], sp["elevation"], strict=True):
                if e <= 0:
                    row.append(None)
                    continue
                polys = []
                for w in unit.windows_of(r.id):
                    if e <= ctxs[w.id].horizon.at(np.array([a]))[0]:
                        continue
                    p = sun_patch_polygon(unit, w, float(a), float(e))
                    if p is not None:
                        polys.append(p)
                if not polys:
                    row.append(None)
                    continue
                u = unary_union(polys)
                g = max(u.geoms, key=lambda q: q.area) if isinstance(u, MultiPolygon) else u
                row.append([[round(x, 3), round(y, 3)] for x, y in g.exterior.coords])
            patches[r.id].append(row)
    return {"dates": dates, "hours": hours, "sun_position": pos, "patches": patches}


def generate(
    unit: Unit,
    models: DwellModels,
    weather: pd.DataFrame,
    out_dir: Path,
    data_kind: str,
    seed: int = 0,
    label: str | None = None,
    sobol: bool = True,
) -> dict[str, Any]:
    t_start = time.time()
    rng = np.random.default_rng(seed)
    post = models.hidden.posterior(unit)
    ref = reference_periods(weather)
    year = ref["typical_year"]
    wd = daily_weather(weather)
    o = PredictOptions(n_mc=6)
    samples = [post.sample(rng) for _ in range(12)]
    from hybrid.priors import default_assignment

    default = default_assignment(unit)
    missing: set[str] = set()

    # ---------------- sun: typical year ----------------
    start = pd.Timestamp(f"{year}-01-01", tz=TZ)
    days = 366 if pd.Timestamp(f"{year}-12-31").dayofyear == 366 else 365
    ps = predict_sun(unit, start, days, weather, rng, o)
    sun_rooms: dict[str, dict[str, Any]] = {}
    tm_sun = models.targets["sun"]
    hw_sun = tm_sun.halfwidth("room")
    ctxs = window_contexts(unit)
    for rid, df in ps.items():
        ds, dc = _doy(df.index)
        extra = pd.DataFrame(
            {
                "phys_nominal": df["physics"],
                "phys_mc_mean": df["mc_mean"],
                "phys_mc_std": df["mc_std"],
                "base_sunpath_only": df["sunpath_only"],
                "wx_sunfrac": wd["wx_sunfrac"].reindex(df.index).to_numpy(),
                "wx_doy_sin": ds,
                "wx_doy_cos": dc,
            },
            index=df.index,
        )
        rows = _rows(unit, rid, extra)
        missing |= set(tm_sun.columns) - set(rows.columns)
        pred = np.clip(tm_sun.predict(rows), 0, None)
        months = np.array([pd.Timestamp(d).month for d in df.index])
        monthly = [round(float(pred[months == m].mean()), 2) for m in range(1, 13)]
        win = pred[np.isin(months, [12, 1, 2])].mean()
        summ = pred[np.isin(months, [6, 7, 8])].mean()
        # clear-sky potential at the winter solstice (physics, no clouds)
        sol = pd.Timestamp(f"{year}-12-21", tz=TZ)
        clr = weather.copy()
        clr["dni"] = clr["dni_clear"]
        pclr = predict_sun(unit, sol, 1, clr, rng, PredictOptions(n_mc=2))[rid]["physics"].iloc[0]
        sun_rooms[rid] = {
            "winter_sun_h": _iv(max(win, 0), hw_sun, "conformal_room"),
            "summer_sun_h": _iv(max(summ, 0), hw_sun, "conformal_room"),
            "monthly_sun_h": monthly,
            "clear_sky_winter_solstice_h": round(float(pclr), 2),
            "daylight_factor_pct": round(average_daylight_factor(unit, rid, ctxs), 2),
            "quantity": "direct-sun hours/day at the main-window sill (typical-year weather)",
        }
    for r in sun_rooms.values():
        for k in ("winter_sun_h", "summer_sun_h"):
            r[k]["lo"] = max(r[k]["lo"], 0.0)

    # ---------------- noise ----------------
    pn = predict_noise(unit, samples, default, rng, o, {r.id: -99.0 for r in unit.rooms})
    mapa = post.map()
    closed = predict_room_noise(unit, NoiseParams(mapa["glazing"], mapa["frame"], mapa["wall"]))
    openw = predict_room_noise(unit, NoiseParams(mapa["glazing"], mapa["frame"], mapa["wall"], open_fraction=0.08))
    noise_rooms, audio = {}, {}
    near_flow = 0.0
    for rd in unit.roads:
        if any(Point(w.cx, w.cy).distance(Point(*rd.coords[0])) < 1e9 for w in unit.windows):
            from shapely.geometry import LineString

            d = min(LineString(rd.coords).distance(Point(w.cx, w.cy)) for w in unit.windows)
            if d < 120:
                near_flow += (rd.aadt or AADT_BY_CLASS.get(rd.road_class, 1000)) * HOURLY_TRAFFIC_PROFILE[2] / 60.0
    transit_2am = sum(t.night_trips_per_hour[2] for t in unit.transit)
    bg = 22.0
    for rid, v in pn.items():
        raw, sd = v["mc_raw_mean"], v["mc_raw_std"]
        pred_c = float(10 * np.log10(10 ** (raw / 10) + 10 ** (bg / 10)))
        lo_c = float(10 * np.log10(10 ** ((raw - 1.645 * sd) / 10) + 10 ** (bg / 10)))
        hi_c = float(10 * np.log10(10 ** ((raw + 1.645 * sd) / 10) + 10 ** (bg / 10)))
        ol = float(10 * np.log10(10 ** (openw[rid]["night_laeq"] / 10) + 10 ** (bg / 10)))
        delta = ol - float(10 * np.log10(10 ** (closed[rid]["night_laeq"] / 10) + 10 ** (bg / 10)))
        noise_rooms[rid] = {
            "night_laeq_closed": {
                "pred": round(pred_c, 1),
                "lo": round(lo_c, 1),
                "hi": round(hi_c, 1),
                "interval_kind": "physics_ensemble",
            },
            "night_laeq_open": {
                "pred": round(pred_c + delta, 1),
                "lo": round(lo_c + delta, 1),
                "hi": round(hi_c + delta, 1),
                "interval_kind": "physics_ensemble",
            },
            "outdoor_night_facade": round(v["outdoor_night"], 1),
            "attribution_db": {k: round(x, 1) for k, x in v["attribution_db"].items() if x > -50},
            "hourly_closed": [round(float(x), 1) for x in closed[rid]["indoor_hourly"]],
            "includes_background_dba": bg,
            "who_guideline_note": WHO_NOTE,
        }
        files = {}
        for tag, res in (("closed", closed), ("open", openw)):
            x = synthesize(
                res[rid]["indoor_band_night"],
                near_flow,
                seed=seed + len(tag),
                transit_events=1 if transit_2am > 0.5 else 0,
            )
            rel = f"audio/{rid}_0200_{tag}.wav"
            write_wav(out_dir / rel, x)
            files[tag] = rel
        audio[rid] = {**files, "label": "Illustrative synthesis, not a recording"}

    # ---------------- heat ----------------
    tm_heat = models.targets["heat"]
    js = pd.Timestamp(f"{year}-06-01", tz=TZ)
    ph = predict_heat(unit, js, 92, weather, samples[:6], default, rng)
    hw = predict_heat(
        unit,
        ref["heatwave_start"].tz_localize(TZ) if ref["heatwave_start"].tzinfo is None else ref["heatwave_start"],
        ref["heatwave_days"],
        weather,
        samples[:6],
        default,
        rng,
    )
    heat_rooms = {}
    for rid in [k for k in ph if not k.startswith("_")]:
        out = {}
        for tag, hres in (("typical", ph), ("heatwave", hw)):
            df = hres[rid]
            ds, dc = _doy(df.index)
            extra = pd.DataFrame(
                {
                    "phys_default": df["physics_default"],
                    "phys_mc_mean": df["mc_mean"],
                    "phys_mc_std": df["mc_std"],
                    "base_outdoor_max": hres["_outdoor_max"].reindex(df.index).to_numpy(),
                    "wx_tmax": wd["wx_tmax"].reindex(df.index).to_numpy(),
                    "wx_tmean": wd["wx_tmean"].reindex(df.index).to_numpy(),
                    "wx_ghi": wd["wx_ghi"].reindex(df.index).to_numpy(),
                    "wx_doy_sin": ds,
                    "wx_doy_cos": dc,
                },
                index=df.index,
            )
            rows = _rows(unit, rid, extra)
            missing |= set(tm_heat.columns) - set(rows.columns)
            out[tag] = (tm_heat.predict(rows), df)
        pred_t, df_t = out["typical"]
        pred_h, _ = out["heatwave"]
        shift = float(np.mean(pred_t - df_t["mc_mean"].to_numpy()))
        # hours above thresholds from the ensemble-mean peaks shifted by the hybrid correction (approximation)
        heat_rooms[rid] = {
            "typical_summer_peak": _iv(float(np.mean(pred_t)), tm_heat.halfwidth("room"), "conformal_room"),
            "heatwave_peak": _iv(float(np.max(pred_h)), tm_heat.halfwidth("row"), "conformal_row"),
            "days_peak_above_26_typical_summer": int(np.sum(pred_t > 26)),
            "days_peak_above_28_typical_summer": int(np.sum(pred_t > 28)),
            "hybrid_correction_c": round(shift, 2),
        }

    # ---------------- what we couldn't see ----------------
    unc = {}
    if sobol:
        hw0 = ref["heatwave_start"]
        hw0 = (hw0.tz_localize(TZ) if hw0.tzinfo is None else hw0).tz_convert("UTC")
        wk = weather.loc[hw0 - pd.Timedelta(days=3) : hw0 + pd.Timedelta(days=5)]
        for room in unit.rooms:
            if not unit.walls_of(room.id):
                continue
            s = room_sobol(unit, room.id, post, wk, n_noise=128, n_heat=24, seed=seed)
            items = []
            pg = np.prod([post.glazing[w.id] for w in unit.windows_of(room.id)], axis=0)
            pf = np.prod([post.frame[w.id] for w in unit.windows_of(room.id)], axis=0)
            dists = {
                "glazing": dict(zip(GLAZING_TYPES, (pg / pg.sum()).round(3).tolist(), strict=True)),
                "frame": dict(zip(FRAME_TYPES, (pf / pf.sum()).round(3).tolist(), strict=True)),
                "wall": dict(zip(WALL_TYPES, post.wall.round(3).tolist(), strict=True)),
            }
            shares = {}
            for tgt, params in (("noise", NOISE_PARAMS), ("heat", HEAT_PARAMS)):
                st = np.clip(np.array(s[tgt]["ST"]), 0, None)
                tot = st.sum() if st.sum() > 0 else 1.0
                shares[tgt] = {p: float(x / tot) for p, x in zip(params, st, strict=True)}
            texts = {
                "glazing": "We could not confirm the glazing (single/double/triple) from the video; the "
                "distribution shown combines building age and visible cues (pane reflections, tint).",
                "frame": "Window seal quality (draughts) is not visible; it changes how much street noise and "
                "outdoor air get in.",
                "wall": "Wall construction (wood frame, brick, concrete) is inferred from age, type and wall "
                "thickness at the windows; it affects heat storage and sound insulation.",
            }
            for prop in ("glazing", "frame", "wall"):
                items.append(
                    {
                        "property": prop,
                        "posterior": dists[prop],
                        "variance_share": {
                            "noise": round(shares["noise"][prop], 3),
                            "heat": round(shares["heat"][prop], 3),
                        },
                        "explanation": texts[prop],
                    }
                )
            items.append(
                {
                    "property": "other_inputs",
                    "posterior": {},
                    "variance_share": {
                        "noise": round(sum(shares["noise"][p] for p in NOISE_PARAMS[3:]), 3),
                        "heat": round(sum(shares["heat"][p] for p in HEAT_PARAMS[3:]), 3),
                    },
                    "explanation": "Traffic volume, vehicle emissions, sound incidence, internal heat gains, "
                    "blind use and wall U-value are also uncertain.",
                }
            )
            unc[room.id] = {"what_we_couldnt_see": items}

    orient = group_labels(unit, unit.rooms[0].id)["g_orient"]
    report = {
        "schema": "dwell-report/1",
        "generated_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "data_kind": data_kind,
        "disclaimer": DISCLAIMER,
        "unit": {
            "id": unit.id,
            "label": label or unit.id,
            "floor": unit.floor,
            "building_kind": unit.building_kind,
            "year_built": unit.year_built,
            "main_orientation": orient,
            "has_ac": unit.has_ac,
        },
        "geometry": _geometry(unit),
        "sun": {**_sun_viewer(unit, 2026), "rooms": sun_rooms},
        "noise": {"rooms": noise_rooms, "audio": audio},
        "heat": {"rooms": heat_rooms},
        "uncertainty": unc,
        "reference_periods": {
            "typical_year": year,
            "heatwave_start": str(ref["heatwave_start"].date()),
            "heatwave_days": ref["heatwave_days"],
            "heatwave_mean_tmax_c": round(ref["heatwave_mean_tmax"], 1),
        },
        "provenance": {
            **git_commit(),
            "model": models.trained_on,
            "calibration": models.trained_on,
            "missing_features": sorted(missing),
            "generation_seconds": round(time.time() - t_start, 1),
        },
    }
    _ = NIGHT_HOURS
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    return report
