"""Higher-fidelity "world" simulator producing synthetic in-home sensor data.

It deliberately includes effects the fast Dwell physics does NOT model, so residual models and
uncertainty can be tested (and so synthetic results are not trivially perfect):

sun      1-min resolution; sub-hourly cloud intermittency (Markov chain around the hourly
         sunshine fraction); blinds closed on some days; sensor placement offsets; true trees
         and true building heights.
noise    day-to-day traffic variation; minute-scale pass-by intermittency; street-canyon
         reflection gain; true incidence correction and room absorption; indoor background
         (fridge/HVAC) and occupant events; windows opened on warm nights; MEMS mic self-noise
         floor and residual calibration error.
thermal  true U-values/g-values/infiltration; party-wall coupling to neighbours; random
         internal-gain level; night ventilation and blinds behaviour; AC use; sensor bias/noise.

All behavioural/measurement parameters are ASSUMPTIONS (see DECISIONS.md, D-012).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.scene import Unit
from physics.acoustics.levels import db_sum
from physics.acoustics.model import NoiseParams, predict_room_noise
from physics.sun.daylight import SENSOR_DEPTH_BEHIND_GLASS, sensor_window, sun_on_windows, window_contexts
from physics.sun.obstruction import vertical_sky_view_factor
from physics.sun.solar import solar_position
from physics.thermal.model import ThermalParams, predict_room_temperatures, window_irradiance

TZ = "America/Toronto"
TAU_VIS = {"single": 0.88, "double": 0.79, "double_lowe": 0.71, "triple": 0.66}
K_BEAM, K_DIFF = 100.0, 120.0  # luminous efficacy lm/W (approx.)
MIC_FLOOR_MEAN = 33.0  # dBA, INMP441 self-noise equivalent (94 dB - 61 dB SNR)


@dataclass
class Deployment:
    start: pd.Timestamp  # local midnight, tz-aware
    days: int


def _markov_sun(rng: np.random.Generator, frac: np.ndarray, mean_run_min: float = 12.0) -> np.ndarray:
    """Binary minute series with time-varying stationary probability ``frac``."""
    n = len(frac)
    out = np.zeros(n, bool)
    state = rng.random() < frac[0]
    for i in range(n):
        p = frac[i]
        if p <= 0.001:
            state = False
        elif p >= 0.999:
            state = True
        else:
            # on->off rate fixed by the mean sunny-spell length; off->on chosen so stationary prob = p
            q_off = min(1.0 / mean_run_min, 1.0)
            q_on = min(q_off * p / (1 - p), 1.0)
            if state and rng.random() < q_off:
                state = False
            elif not state and rng.random() < q_on:
                state = True
        out[i] = state
    return out


def simulate_unit(rng: np.random.Generator, unit: Unit, weather: pd.DataFrame, dep: Deployment) -> dict:
    """Returns {"rooms": {room_id: minute DataFrame}, "truth": {...}, "kit": {...}}."""
    t0 = dep.start.tz_convert("UTC")
    t1 = t0 + pd.Timedelta(days=dep.days)
    mins = pd.date_range(t0, t1, freq="1min", inclusive="left")
    wx = weather.loc[t0 - pd.Timedelta(days=8) : t1 + pd.Timedelta(hours=1)]
    hourly_idx = mins.floor("h")
    wh = wx.reindex(hourly_idx)

    # ---------------- sun ----------------
    sp = solar_position(mins, unit.lat, unit.lon)
    offsets = {}
    for r in unit.rooms:
        sw = sensor_window(unit, r.id)
        if sw is not None:
            offsets[sw.id] = (
                float(rng.normal(0, 0.12 * sw.width)),
                float(np.clip(rng.normal(SENSOR_DEPTH_BEHIND_GLASS, 0.03), 0.03, 0.2)),
            )
    ctxs = window_contexts(unit)
    sow = sun_on_windows(unit, mins, ctxs, solpos=sp, sensor_offsets=offsets)
    with np.errstate(divide="ignore", invalid="ignore"):
        frac_h = np.clip(wh["dni"].to_numpy() / wh["dni_clear"].to_numpy(), 0, 1)
    frac_h = np.where(wh["dni_clear"].to_numpy() > 5, frac_h, 0.0)
    frac_h = np.nan_to_num(frac_h)
    sun_vis = _markov_sun(rng, frac_h)
    el = sp["elevation"].to_numpy()
    sin_el = np.clip(np.sin(np.radians(el)), 0, 1)
    dni_clear = np.nan_to_num(wh["dni_clear"].to_numpy())
    dhi = np.nan_to_num(wh["dhi"].to_numpy())
    local_days = mins.tz_convert(TZ).normalize()
    uniq_days = local_days.unique()

    rooms_out: dict[str, pd.DataFrame] = {}
    truth: dict[str, dict] = {}
    kit_cal = {}

    # ---------------- noise (hourly physics with TRUE params + extras) ----------------
    c_inc = float(rng.uniform(1.0, 5.0))
    noise_true = predict_room_noise(
        unit,
        NoiseParams(
            {w.id: w.glazing for w in unit.windows},
            {w.id: w.frame for w in unit.windows},
            unit.walls[0].wall_type,
            c_inc=c_inc,
        ),
    )
    noise_open = predict_room_noise(
        unit,
        NoiseParams(
            {w.id: w.glazing for w in unit.windows},
            {w.id: w.frame for w in unit.windows},
            unit.walls[0].wall_type,
            c_inc=c_inc,
            open_fraction=0.08,
        ),
    )
    # canyon gain for facades facing nearby buildings
    canyon = {}
    for ctx in ctxs:
        rel = ((ctx.horizon.az - ctx.window.azimuth + 180) % 360) - 180
        med = float(np.median(np.clip(ctx.horizon.elevation[np.abs(rel) < 45], 0, 90)))
        canyon[ctx.window.room_id] = 2.0 * np.clip(med / 30.0, 0, 1) + float(rng.normal(0, 0.5))
    day_factor = {d: float(rng.normal(0, 1.2)) for d in uniq_days}  # dB, day-to-day traffic variation

    # ---------------- thermal (hourly, TRUE params + behaviour) ----------------
    th_idx = pd.date_range(t0 - pd.Timedelta(days=7), t1, freq="1h", inclusive="left")
    wth = weather.reindex(th_idx).interpolate(limit_direction="both")
    warm_nights = {}
    loc_th = th_idx.tz_convert(TZ)
    night_min = pd.Series(wth["temp_c"].to_numpy(), index=loc_th).groupby(loc_th.normalize()).min()
    for d, v in night_min.items():
        warm_nights[d] = bool(v > 16.0)
    opens_windows = bool(rng.random() < 0.6) and not unit.has_ac
    vent_ach = float(rng.uniform(1.5, 5.0)) if opens_windows else 0.0
    party_h = float(rng.uniform(0.5, 1.5))  # W/K per m2 floor to neighbours
    tp = ThermalParams(
        {w.id: w.glazing for w in unit.windows},
        {w.id: w.frame for w in unit.windows},
        unit.walls[0].wall_type,
        u_wall=unit.walls[0].u_value,
        internal_gain_scale=float(rng.lognormal(0, 0.35)),
        night_vent_ach=vent_ach,
        blinds_factor=float(rng.uniform(0.6, 1.0)),
        ac_setpoint=float(rng.uniform(22.5, 26.0)) if unit.has_ac and rng.random() < 0.85 else None,
        heat_setpoint=float(rng.uniform(19.5, 22.5)),
    )
    irr = window_irradiance(unit, wth)
    temps = predict_room_temperatures(unit, wth, tp, irr=irr, spinup_days=0, party=party_h)

    for r in unit.rooms:
        if not unit.walls_of(r.id):
            continue
        sw = sensor_window(unit, r.id)
        assert sw is not None
        # --- lux
        beam = sow[sw.id]["sensor_beam"].to_numpy() * sun_vis
        blinds_days = {
            d: bool(sw.has_blinds and rng.random() < (0.3 if r.kind == "bedroom" else 0.12)) for d in uniq_days
        }
        blinds = np.array([blinds_days[d] for d in local_days])
        ctx = next(c for c in ctxs if c.window.id == sw.id)
        svf = vertical_sky_view_factor(ctx.horizon, sw.azimuth)
        tau = TAU_VIS[sw.glazing]
        e_beam = beam * dni_clear * 0.95 * sin_el * K_BEAM * tau
        e_diff = dhi * (0.6 * svf) * K_DIFF * tau * (1 + 0.6 * (1 - sun_vis) * (dhi > 0))
        lux = (e_beam + e_diff) * np.where(blinds, 0.08, 1.0) * rng.lognormal(0, 0.03, len(mins))
        lux = np.where(el > -3, lux, 0.0) + rng.uniform(0, 0.5, len(mins))
        lux = np.minimum(lux, 120000.0)
        true_sensor_sun = (beam > 0.5) & (el > 0)

        # --- noise (minute)
        h_loc = mins.tz_convert(TZ).hour.to_numpy()
        hour_level = noise_true[r.id]["indoor_hourly"]
        hour_level_open = noise_open[r.id]["indoor_hourly"]
        night_flag = (h_loc >= 23) | (h_loc < 7)
        night_day = (mins.tz_convert(TZ) - pd.Timedelta(hours=12)).normalize()  # night "belongs" to prior evening
        open_night = np.array([opens_windows and warm_nights.get(d, False) and r.kind == "bedroom" for d in night_day])
        base = np.where(open_night & night_flag, hour_level_open[h_loc], hour_level[h_loc])
        base = base + canyon.get(r.id, 0.0) + np.array([day_factor.get(d, 0.0) for d in local_days])
        # intermittency: gamma-distributed minute energy around the hourly mean
        from physics.acoustics.model import HOURLY_TRAFFIC_PROFILE

        veh_per_min = np.maximum(HOURLY_TRAFFIC_PROFILE[h_loc] * 10000 / 60.0, 0.15)
        e_min = 10 ** (base / 10) * rng.gamma(veh_per_min, 1.0 / veh_per_min)
        bg = float(rng.uniform(17.0, 29.0))
        occ_p = np.where(night_flag, 0.015 if r.kind == "bedroom" else 0.005, 0.04)
        occ = rng.random(len(mins)) < occ_p
        occ_level = np.where(night_flag, rng.uniform(32, 52, len(mins)), rng.uniform(45, 68, len(mins)))
        true_room = 10 * np.log10(e_min + 10 ** (bg / 10) + occ * 10 ** (occ_level / 10))
        floor = float(rng.normal(MIC_FLOOR_MEAN, 1.0))
        cal_err = float(rng.normal(0, 1.5))
        measured = 10 * np.log10(10 ** (true_room / 10) + 10 ** (floor / 10)) + cal_err
        spread = rng.uniform(3, 9, len(mins))
        lamax = measured + spread * (1 + occ)
        la90 = measured - spread * 0.7

        # --- temperature (hourly -> minute), sensor bias/noise, radiant error when sill sunlit
        t_air = temps[r.id]["t_air"].reindex(mins, method="ffill").to_numpy()
        t_air = pd.Series(t_air).interpolate().to_numpy()
        t_bias = float(rng.normal(0.0, 0.2))
        t_meas = t_air + 0.3 + t_bias + rng.normal(0, 0.08, len(mins))
        rh = np.clip(55 + rng.normal(0, 5) - 2.0 * (t_meas - 22), 15, 95)

        rooms_out[r.id] = pd.DataFrame(
            {
                "lux": np.round(lux, 1),
                "temp_c": np.round(t_meas, 2),
                "rh_pct": np.round(rh, 1),
                "laeq": np.round(measured, 1),
                "lamax": np.round(lamax, 1),
                "la90": np.round(la90, 1),
            },
            index=mins,
        )
        traffic_only = base + 10 * np.log10(rng.gamma(veh_per_min, 1.0 / veh_per_min))
        truth[r.id] = {
            "true_sensor_sun_min": pd.Series(true_sensor_sun.astype(float), index=mins),
            "blinds_days": blinds_days,
            "open_window_minutes": pd.Series(open_night & night_flag, index=mins),
            "traffic_indoor_min": pd.Series(traffic_only, index=mins),
            "t_air_true": temps[r.id]["t_air"],
        }
        kit_cal[r.id] = {"mic_floor": floor, "cal_err_db": cal_err, "temp_bias": t_bias}
    return {
        "rooms": rooms_out,
        "truth": truth,
        "kit": kit_cal,
        "behaviour": {
            "opens_windows": opens_windows,
            "vent_ach": vent_ach,
            "c_inc": c_inc,
            "ac": tp.ac_setpoint,
            "gain_scale": tp.internal_gain_scale,
        },
    }


def total_db(levels: np.ndarray) -> float:
    return float(db_sum(levels))
