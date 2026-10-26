"""Per-room Sobol decomposition of night-noise and summer-heat predictions w.r.t. hidden properties
and uncertain physical inputs ("what we couldn't see")."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
from scipy.stats import norm
from shapely.geometry import Polygon

from core.scene import FRAME_TYPES, GLAZING_TYPES, WALL_TYPES, Unit
from hybrid.priors import HiddenPosterior, _norm
from hybrid.sensitivity import categorical, sobol_indices
from physics.acoustics.insulation import absorption_area, facade_r, indoor_level
from physics.acoustics.levels import A_WEIGHT, db_mean, db_sum
from physics.acoustics.model import NIGHT_HOURS, Obstacles, build_sources, incident_levels
from physics.thermal.model import (
    ThermalParams,
    daily_heat_metrics,
    predict_room_temperatures,
    window_irradiance,
)

NOISE_PARAMS = ["glazing", "frame", "wall", "incidence_term", "emission", "traffic_volume"]
HEAT_PARAMS = ["glazing", "frame", "wall", "wall_u_value", "internal_gains", "blinds_use"]


def _unit_probs(post: HiddenPosterior, room_id: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    ids = [k for k in post.glazing if room_id is None or k.startswith(room_id)] or list(post.glazing)
    pg = _norm(np.prod([post.glazing[i] for i in ids], axis=0) ** (1 / len(ids)))
    pf = _norm(np.prod([post.frame[i] for i in ids], axis=0) ** (1 / len(ids)))
    return pg, pf


def noise_function(u: Unit, room_id: str, post: HiddenPosterior, counted: bool):
    obs = Obstacles.from_buildings(u.context_buildings)
    srcs = build_sources(u)
    kinds = np.array([s.kind == "road" for s in srcs])
    room = u.room(room_id)
    a_abs = absorption_area(Polygon(room.polygon).area * room.ceiling_height, room.furnishing)
    walls = []
    for wall in u.walls_of(room_id):
        az = np.radians(wall.azimuth)
        rcv = np.array([wall.cx + 0.5 * np.sin(az), wall.cy + 0.5 * np.cos(az), wall.base_z + 1.5])
        inc = incident_levels(rcv, srcs, obs)
        stack = np.stack([inc[s.id][NIGHT_HOURS] for s in srcs])  # (S, 8, B)
        wins = [w for w in u.windows_of(room_id) if abs(((w.azimuth - wall.azimuth + 180) % 360) - 180) < 1]
        walls.append((stack, wins, wall.length * wall.height))
    pg, pf = _unit_probs(post, room_id)
    pw = post.wall
    tv_sd = 0.15 if counted else 0.4

    def f(x: np.ndarray) -> np.ndarray:
        g = categorical(x[:, 0], pg)
        fr = categorical(x[:, 1], pf)
        wt = categorical(x[:, 2], pw)
        c_inc = 6.0 * x[:, 3]
        emis = norm.ppf(np.clip(x[:, 4], 1e-6, 1 - 1e-6)) * 2.0
        tv = 10 * np.log10(np.exp(norm.ppf(np.clip(x[:, 5], 1e-6, 1 - 1e-6)) * tv_sd))
        out = np.empty(len(x))
        cache: dict = {}
        for i in range(len(x)):
            key = (g[i], fr[i], wt[i])
            if key not in cache:
                cache[key] = [
                    facade_r(
                        s_area,
                        WALL_TYPES[wt[i]],
                        [(w.width * w.height, GLAZING_TYPES[g[i]], FRAME_TYPES[fr[i]], w.frame_fraction) for w in wins],
                    )
                    for _, wins, s_area in walls
                ]
            tot = []
            for (stack, _, s_area), r in zip(walls, cache[key], strict=True):
                shift = emis[i] + np.where(kinds, tv[i], 0.0)
                lin = indoor_level(stack + shift[:, None, None], r, s_area, a_abs, c_inc[i])
                tot.append(db_sum(lin + A_WEIGHT, axis=-1))  # (S, 8)
            hourly = db_sum(np.concatenate(tot, axis=0), axis=0)
            out[i] = db_mean(hourly)
        return out

    return f


def heat_function(u: Unit, room_id: str, post: HiddenPosterior, weather_week: pd.DataFrame):
    v = copy.deepcopy(u)
    v.rooms = [r for r in v.rooms if r.id == room_id]
    v.windows = [w for w in v.windows if w.room_id == room_id]
    v.walls = [w for w in v.walls if w.room_id == room_id]
    irr = window_irradiance(v, weather_week)
    pg, pf = _unit_probs(post, room_id)
    pw = post.wall
    ac = 24.0 if u.has_ac else None
    from physics.thermal.model import U_WALL_DEFAULT

    def f(x: np.ndarray) -> np.ndarray:
        out = np.empty(len(x))
        for i in range(len(x)):
            g = GLAZING_TYPES[categorical(x[i : i + 1, 0], pg)[0]]
            fr = FRAME_TYPES[categorical(x[i : i + 1, 1], pf)[0]]
            wt = WALL_TYPES[categorical(x[i : i + 1, 2], pw)[0]]
            uw = U_WALL_DEFAULT[wt] * float(np.exp(norm.ppf(np.clip(x[i, 3], 1e-6, 1 - 1e-6)) * 0.35))
            gain = float(np.exp(norm.ppf(np.clip(x[i, 4], 1e-6, 1 - 1e-6)) * 0.35))
            blinds = 0.6 + 0.4 * float(x[i, 5])
            tp = ThermalParams(
                {w.id: g for w in v.windows},
                {w.id: fr for w in v.windows},
                wt,
                u_wall=uw,
                internal_gain_scale=gain,
                blinds_factor=blinds,
                ac_setpoint=ac,
                heat_setpoint=None,
            )
            res = predict_room_temperatures(v, weather_week, tp, irr=irr, spinup_days=3)[room_id]
            out[i] = float(daily_heat_metrics(res.iloc[72:])["peak"].mean())
        return out

    return f


def room_sobol(
    u: Unit,
    room_id: str,
    post: HiddenPosterior,
    weather_week: pd.DataFrame | None,
    n_noise: int = 256,
    n_heat: int = 64,
    seed: int = 0,
) -> dict:
    counted = all(r.aadt is not None for r in u.roads)
    out = {}
    fn = noise_function(u, room_id, post, counted)
    rn = sobol_indices(fn, len(NOISE_PARAMS), n_noise, seed=seed, n_boot=50)
    out["noise"] = {
        "params": NOISE_PARAMS,
        "ST": rn["ST"].tolist(),
        "S1": rn["S1"].tolist(),
        "ST_sd": rn["ST_sd"].tolist(),
        "var": rn["var"],
    }
    if weather_week is not None:
        fh = heat_function(u, room_id, post, weather_week)
        rh = sobol_indices(fh, len(HEAT_PARAMS), n_heat, seed=seed, n_boot=50)
        out["heat"] = {
            "params": HEAT_PARAMS,
            "ST": rh["ST"].tolist(),
            "S1": rh["S1"].tolist(),
            "ST_sd": rh["ST_sd"].tolist(),
            "var": rh["var"],
        }
    return out
