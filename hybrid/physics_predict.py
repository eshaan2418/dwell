"""Physics predictions for an OBSERVED unit over a deployment period.

Monte Carlo over (a) hidden-property samples from the posterior and (b) uncertain physical inputs
(facade azimuth error, neighbour heights, emission offset, traffic scale, incidence term). Returns
per-room daily/nightly ensembles plus the baseline variants used in M8:

  physics_default   default materials, nominal inputs (no inference)
  physics_inferred  posterior/MC ensemble mean
  sunpath_only      sun geometry with no obstruction model (single-purpose sun app analogue)
  noisemap_only     outdoor facade night level - 25 dB generic insulation (city noise-map analogue)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from core.scene import Unit
from hybrid.priors import HiddenPosterior, default_assignment
from physics.acoustics.levels import db_sum
from physics.acoustics.model import NIGHT_HOURS, NoiseParams, build_sources, predict_room_noise
from physics.sun.daylight import room_sun_timeseries, sun_on_windows, window_contexts
from physics.sun.solar import solar_position
from physics.thermal.model import (
    ThermalParams,
    daily_heat_metrics,
    predict_room_temperatures,
    window_irradiance,
)

TZ = "America/Toronto"
BACKGROUND_DBA = 22.0  # default indoor background (fridge/HVAC) assumed by the physics layer
GENERIC_FACADE_DB = 25.0


@dataclass
class PredictOptions:
    n_mc: int = 12
    sun_step_min: int = 10
    use_obstruction: bool = True
    use_transit: bool = True
    use_trees: bool = True
    az_sd: float = 4.0
    height_logsd: float = 0.12


def sunshine_prob(weather: pd.DataFrame, times: pd.DatetimeIndex) -> pd.Series:
    w = weather.reindex(times.floor("h"))
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.clip(w["dni"].to_numpy() / w["dni_clear"].to_numpy(), 0, 1)
    p = np.where(w["dni_clear"].to_numpy() > 5, p, 0.0)
    return pd.Series(np.nan_to_num(p), index=times)


def _perturb_geometry(u: Unit, rng: np.random.Generator, o: PredictOptions) -> Unit:
    v = copy.deepcopy(u)
    da = float(rng.normal(0, o.az_sd))
    for w in v.windows:
        w.azimuth = (w.azimuth + da) % 360
    for wl in v.walls:
        wl.azimuth = (wl.azimuth + da) % 360
    for b in v.context_buildings:
        if b.id != v.building_id:
            b.height *= float(rng.lognormal(0, o.height_logsd))
    return v


def _local_days(times: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(times.tz_convert(TZ).date)


def predict_sun(
    obs: Unit, start: pd.Timestamp, days: int, weather: pd.DataFrame, rng: np.random.Generator, o: PredictOptions
) -> dict[str, pd.DataFrame]:
    t = pd.date_range(
        start.tz_convert("UTC"),
        start.tz_convert("UTC") + pd.Timedelta(days=days),
        freq=f"{o.sun_step_min}min",
        inclusive="left",
    )
    sp = solar_position(t, obs.lat, obs.lon)
    p = sunshine_prob(weather, t).to_numpy()
    step_h = o.sun_step_min / 60.0
    dkeys = _local_days(t)

    def run(u: Unit, use_obs: bool) -> dict[str, pd.Series]:
        if not use_obs:
            u = copy.deepcopy(u)
            u.context_buildings = []
            u.trees = []
        ctx = window_contexts(u)
        pw = sun_on_windows(u, t, ctx, use_trees=o.use_trees and use_obs, solpos=sp)
        rs = room_sun_timeseries(u, t, pw)
        return {rid: pd.Series(df["sensor_sun"].to_numpy() * p * step_h).groupby(dkeys).sum() for rid, df in rs.items()}

    nominal = run(obs, o.use_obstruction)
    sunpath = run(obs, False)
    ens = [run(_perturb_geometry(obs, rng, o), o.use_obstruction) for _ in range(max(o.n_mc // 2, 3))]
    out = {}
    for rid in nominal:
        m = np.stack([e[rid].to_numpy() for e in ens])
        out[rid] = pd.DataFrame(
            {
                "physics": nominal[rid].to_numpy(),
                "mc_mean": m.mean(0),
                "mc_std": m.std(0),
                "sunpath_only": sunpath[rid].to_numpy(),
            },
            index=nominal[rid].index,
        )
    return out


def _with_floor(l_dba: np.ndarray | float, floor: float, bg: float = BACKGROUND_DBA) -> np.ndarray:
    return db_sum(np.stack(np.broadcast_arrays(np.asarray(l_dba, float), bg, floor)), axis=0)


def predict_noise(
    obs: Unit,
    samples: list[dict[str, Any]],
    default: dict[str, Any],
    rng: np.random.Generator,
    o: PredictOptions,
    kit_floor: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Night L_Aeq (closed windows) per room: physics ensembles with/without the kit floor."""
    u = copy.deepcopy(obs)
    if not o.use_transit:
        u.transit = []
    has_count = {r.id: r.aadt is not None for r in u.roads}
    cache: dict = {}
    base_sources = build_sources(u)
    nom = predict_room_noise(u, NoiseParams(default["glazing"], default["frame"], default["wall"]), base_sources, cache)
    vals: dict[str, list[float]] = {r: [] for r in nom}
    by_kind: dict[str, dict[str, list[float]]] = {r: {} for r in nom}
    for s in samples:
        # uncertain emission and traffic: scale applies to roads without counts more strongly
        emis = float(rng.normal(0, 2.0))
        scale = float(rng.lognormal(0, 0.15 if all(has_count.values()) else 0.4))
        srcs = build_sources(u, aadt_scale=scale, emission_offset_db=emis)
        res = predict_room_noise(
            u, NoiseParams(s["glazing"], s["frame"], s["wall"], c_inc=float(rng.uniform(0, 6))), srcs, {}
        )
        for rid, r in res.items():
            vals[rid].append(r["night_laeq"])
            for k, lv in r["by_kind_hourly"].items():
                by_kind[rid].setdefault(k, []).append(float(10 * np.log10(np.mean(10 ** (lv[NIGHT_HOURS] / 10)))))
    out = {}
    for rid, r in nom.items():
        fl = kit_floor.get(rid, 33.0)
        v = np.array(vals[rid])
        ens_meas = _with_floor(v, fl)
        out[rid] = {
            "physics_default": float(_with_floor(r["night_laeq"], fl)),
            "physics_default_raw": float(r["night_laeq"]),
            "mc_mean": float(10 * np.log10(np.mean(10 ** (ens_meas / 10)))),
            "mc_std": float(np.std(ens_meas)),
            "mc_raw_mean": float(np.mean(v)),
            "mc_raw_std": float(np.std(v)),
            "outdoor_night": float(10 * np.log10(np.mean(10 ** (r["outdoor_facade_hourly"][NIGHT_HOURS] / 10)))),
            "noisemap_only": float(
                _with_floor(
                    10 * np.log10(np.mean(10 ** (r["outdoor_facade_hourly"][NIGHT_HOURS] / 10))) - GENERIC_FACADE_DB, fl
                )
            ),
            "floor": fl,
            "attribution_db": {k: float(np.mean(x)) for k, x in by_kind[rid].items()},
        }
    return out


def predict_heat(
    obs: Unit,
    start: pd.Timestamp,
    days: int,
    weather: pd.DataFrame,
    samples: list[dict[str, Any]],
    default: dict[str, Any],
    rng: np.random.Generator,
) -> dict[str, pd.DataFrame]:
    t0 = start.tz_convert("UTC") - pd.Timedelta(days=7)
    idx = pd.date_range(t0, start.tz_convert("UTC") + pd.Timedelta(days=days), freq="1h", inclusive="left")
    wx = weather.reindex(idx).interpolate(limit_direction="both")
    irr = window_irradiance(obs, wx)
    ac = 24.0 if obs.has_ac else None

    def run(a: dict[str, Any], gain: float = 1.0, blinds: float = 1.0) -> dict[str, pd.Series]:
        tp = ThermalParams(
            a["glazing"],
            a["frame"],
            a["wall"],
            internal_gain_scale=gain,
            blinds_factor=blinds,
            ac_setpoint=ac,
            heat_setpoint=21.0,
        )
        res = predict_room_temperatures(obs, wx, tp, irr=irr, spinup_days=7)
        out = {}
        for rid, df in res.items():
            m = daily_heat_metrics(df.iloc[7 * 24 :])
            out[rid] = m["peak"]
        return out

    nom = run(default)
    ens = [run(s, gain=float(rng.lognormal(0, 0.3)), blinds=float(rng.uniform(0.7, 1.0))) for s in samples]
    out = {}
    for rid in nom:
        m = np.stack([e[rid].to_numpy() for e in ens])
        out[rid] = pd.DataFrame(
            {"physics_default": nom[rid].to_numpy(), "mc_mean": m.mean(0), "mc_std": m.std(0)}, index=nom[rid].index
        )
    out["_outdoor_max"] = wx.iloc[7 * 24 :]["temp_c"].groupby(_local_days(wx.index[7 * 24 :])).max()
    return out


def predict_all(
    obs: Unit,
    post: HiddenPosterior,
    start: pd.Timestamp,
    days: int,
    weather: pd.DataFrame,
    seed: int,
    o: PredictOptions | None = None,
    kit_floor: dict[str, float] | None = None,
) -> dict:
    o = o or PredictOptions()
    rng = np.random.default_rng(seed)
    samples = [post.sample(rng) for _ in range(o.n_mc)]
    default = default_assignment(obs)
    return {
        "sun": predict_sun(obs, start, days, weather, rng, o),
        "noise": predict_noise(obs, samples, default, rng, o, kit_floor or {}),
        "heat": predict_heat(obs, start, days, weather, samples, default, rng),
        "posterior": {
            "glazing": {k: v.tolist() for k, v in post.glazing.items()},
            "frame": {k: v.tolist() for k, v in post.frame.items()},
            "wall": post.wall.tolist(),
        },
    }
