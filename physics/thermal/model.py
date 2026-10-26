"""Unit -> per-room 5R1C thermal models driven by hourly weather.

Each room with exterior exposure is an independent 5R1C zone (party walls/floors to
neighbouring conditioned spaces treated as adiabatic). Solar gains use the window sun model
(beam through the sunlit aperture) plus isotropic sky diffuse scaled by the vertical sky view
factor and ground-reflected irradiance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from core.scene import Unit
from physics.sun.daylight import sun_on_windows, window_contexts
from physics.sun.obstruction import vertical_sky_view_factor
from physics.sun.solar import solar_position, sun_vector
from physics.thermal.rc5r1c import RHO_CP_AIR, RCParams, simulate

U_GLAZING = {"single": 5.0, "double": 2.8, "double_lowe": 1.8, "triple": 1.1}  # whole window W/m2K
G_GLAZING = {"single": 0.85, "double": 0.75, "double_lowe": 0.6, "triple": 0.5}  # normal-incidence g
U_WALL_DEFAULT = {"light_frame": 0.45, "masonry": 1.4, "concrete": 0.8}
MASS_BY_WALL = {"light_frame": "light", "masonry": "heavy", "concrete": "heavy"}
ACH_BY_FRAME = {"tight": 0.15, "average": 0.4, "leaky": 0.9}
GROUND_ALBEDO = 0.2

# internal gains W/m2 by local hour (residential, occupied evening/night)
_INT = np.array([2.5] * 7 + [4.0, 3.0] + [2.0] * 8 + [4.0, 6.0, 6.5, 6.0, 5.0, 4.0, 3.0])
INTERNAL_GAIN_PROFILE = _INT


@dataclass
class ThermalParams:
    glazing: dict[str, str]
    frame: dict[str, str]
    wall_type: str
    u_wall: float | None = None
    internal_gain_scale: float = 1.0
    night_vent_ach: float = 0.0  # extra ACH 22-07 when outdoor < indoor-ish (window opened at night)
    blinds_factor: float = 1.0  # fraction of solar gain admitted (1 = no blinds)
    ac_setpoint: float | None = None
    heat_setpoint: float | None = 20.0
    mass_class: str | None = None
    extra: dict = field(default_factory=dict)


def incidence_modifier(cos_theta: np.ndarray, b0: float = 0.1) -> np.ndarray:
    with np.errstate(divide="ignore"):
        iam = 1 - b0 * (1 / np.clip(cos_theta, 1e-3, 1) - 1)
    return np.clip(iam, 0, 1)


def window_irradiance(unit: Unit, weather: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per window: transmitted-solar driver [W/m2 of glazing] split beam/diffuse, hourly (UTC)."""
    t_mid = weather.index + pd.Timedelta(minutes=30)
    sp = solar_position(t_mid, unit.lat, unit.lon)
    ctxs = window_contexts(unit)
    sow = sun_on_windows(unit, t_mid, ctxs, solpos=sp)
    s = sun_vector(sp["azimuth"].to_numpy(), sp["elevation"].to_numpy())
    out = {}
    for ctx in ctxs:
        w = ctx.window
        n = np.array([np.sin(np.radians(w.azimuth)), np.cos(np.radians(w.azimuth)), 0.0])
        cos_t = np.clip(s @ n, 0, 1)
        frac = sow[w.id]["sunlit_frac"].to_numpy()
        beam = weather["dni"].fillna(0).to_numpy() * cos_t * frac * incidence_modifier(cos_t)
        svf = vertical_sky_view_factor(ctx.horizon, w.azimuth)
        diff = (
            weather["dhi"].fillna(0).to_numpy() * svf * 0.9
            + weather["ghi"].fillna(0).to_numpy() * GROUND_ALBEDO * 0.5 * 0.9
        )
        out[w.id] = pd.DataFrame({"beam": beam, "diffuse": diff}, index=weather.index)
    return out


def room_rc(unit: Unit, room_id: str, p: ThermalParams) -> tuple[RCParams, float, float]:
    room = unit.room(room_id)
    af = Polygon(room.polygon).area
    vol = af * room.ceiling_height
    wins = unit.windows_of(room_id)
    h_w = sum(U_GLAZING[p.glazing.get(w.id, "double")] * w.width * w.height for w in wins)
    wall_area = sum(wl.length * wl.height for wl in unit.walls_of(room_id))
    opaque = max(wall_area - sum(w.width * w.height for w in wins), 0.5)
    u_wall = p.u_wall if p.u_wall is not None else U_WALL_DEFAULT[p.wall_type]
    h_op = u_wall * opaque
    if unit.meta.get("top_floor"):
        h_op += 0.35 * af
    frames = [p.frame.get(w.id, "average") for w in wins] or ["average"]
    ach = float(np.mean([ACH_BY_FRAME[f] for f in frames]))
    rc = RCParams(
        floor_area=af,
        h_tr_w=h_w,
        h_tr_op=h_op,
        mass_class=p.mass_class or MASS_BY_WALL[p.wall_type],
        heat_setpoint=p.heat_setpoint,
        cool_setpoint=p.ac_setpoint,
    )
    return rc, vol, ach


def predict_room_temperatures(
    unit: Unit,
    weather: pd.DataFrame,
    p: ThermalParams,
    irr: dict[str, pd.DataFrame] | None = None,
    tz: str = "America/Toronto",
    spinup_days: int = 7,
    party: float = 0.0,
    theta_party: float = 22.0,
) -> dict[str, pd.DataFrame]:
    """Hourly indoor air temperature per room (index = weather index, UTC)."""
    irr = irr if irr is not None else window_irradiance(unit, weather)
    hours_local = weather.index.tz_convert(tz).hour.to_numpy()
    te = weather["temp_c"].interpolate(limit_direction="both").to_numpy()
    out = {}
    for room in unit.rooms:
        if not unit.walls_of(room.id):
            continue
        rc, vol, ach = room_rc(unit, room.id, p)
        wins = unit.windows_of(room.id)
        phi_sol = np.zeros(len(weather))
        for w in wins:
            g = G_GLAZING[p.glazing.get(w.id, "double")]
            a_gl = w.width * w.height * (1 - w.frame_fraction)
            phi_sol += g * a_gl * (irr[w.id]["beam"].to_numpy() + irr[w.id]["diffuse"].to_numpy())
        phi_sol *= p.blinds_factor
        phi_int = INTERNAL_GAIN_PROFILE[hours_local] * rc.floor_area * p.internal_gain_scale
        night = (hours_local >= 22) | (hours_local < 7)
        ach_t = ach + np.where(night & (te < 24), p.night_vent_ach, 0.0)
        h_ve = RHO_CP_AIR * ach_t * vol / 3600.0
        # spin-up: repeat the first week to initialise the mass node
        hp = party * rc.floor_area
        k = min(spinup_days * 24, len(te))
        tm0 = None
        if k > 0:
            pre = simulate(rc, te[:k], h_ve[:k], phi_int[:k], phi_sol[:k], h_party=hp, theta_party=theta_party)
            tm0 = float(pre["mass"][-1])
        res = simulate(rc, te, h_ve, phi_int, phi_sol, theta_m0=tm0, h_party=hp, theta_party=theta_party)
        out[room.id] = pd.DataFrame(
            {"t_air": res["air"], "t_out": te, "phi_sol": phi_sol, "phi_hc": res["phi_hc"]}, index=weather.index
        )
    return out


def daily_heat_metrics(ts: pd.DataFrame, tz: str = "America/Toronto") -> pd.DataFrame:
    loc = ts["t_air"].copy()
    loc.index = loc.index.tz_convert(tz)
    g = loc.groupby(loc.index.date)
    return pd.DataFrame(
        {
            "peak": g.max(),
            "h_above_26": g.apply(lambda x: float((x > 26).sum())),
            "h_above_28": g.apply(lambda x: float((x > 28).sum())),
        }
    )
