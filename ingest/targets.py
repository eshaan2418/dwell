"""Derived evaluation targets from cleaned 1-min sensor data (identical for real and synthetic).

sun    direct-sun hours/day at the sensor point (kit on the main-window sill): a minute is "sunlit"
       when lux >= THETA x clear-sky beam-on-horizontal illuminance behind glass and lux >= LUX_MIN.
noise  nightly (23:00-07:00 local) L_Aeq (energetic mean of 1-min L_Aeq), L_A90 (10th percentile of
       minute levels), and a 5 %-trimmed L_Aeq robust to occupant events; nights flagged as
       window-open by a heuristic are reported separately.
heat   daily peak indoor temperature = max of 10-min rolling mean; hours above 26/28 C.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from physics.acoustics.levels import db_mean
from physics.sun.solar import clear_sky, solar_position

TZ = "America/Toronto"
THETA = 0.35  # fraction of clear-sky beam illuminance behind glass (calibrated on synthetic data; D-014)
LUX_MIN = 2500.0
K_BEAM = 100.0
TAU_REF = 0.75
MIN_COVERAGE = 0.9


def sun_minutes(d: pd.DataFrame, lat: float, lon: float, theta: float = THETA, lux_min: float = LUX_MIN) -> pd.Series:
    sp = solar_position(d.index, lat, lon)
    cs = clear_sky(d.index, lat, lon)
    el = sp["elevation"].to_numpy()
    e_ref = cs["dni"].to_numpy() * np.clip(np.sin(np.radians(el)), 0, 1) * K_BEAM * TAU_REF
    lux = d["lux"].to_numpy()
    sun = (el > 2) & (lux >= theta * e_ref) & (lux >= lux_min)
    out = pd.Series(np.where(np.isnan(lux), np.nan, sun.astype(float)), index=d.index)
    out[el <= 2] = np.where(np.isnan(lux[el <= 2]), np.nan, 0.0)
    return out


def daily_sun_hours(d: pd.DataFrame, lat: float, lon: float, **kw) -> pd.DataFrame:
    s = sun_minutes(d, lat, lon, **kw)
    loc = s.copy()
    loc.index = loc.index.tz_convert(TZ)
    g = loc.groupby(loc.index.date)
    cov = g.apply(lambda x: x.notna().mean())
    hours = g.apply(lambda x: np.nansum(x) / 60.0)
    df = pd.DataFrame({"sun_h": hours, "coverage": cov})
    return df[df["coverage"] >= MIN_COVERAGE]


def _night_key(idx: pd.DatetimeIndex) -> pd.Index:
    loc = idx.tz_convert(TZ)
    return (loc - pd.Timedelta(hours=12)).normalize().date  # night belongs to the preceding evening


def nightly_noise(d: pd.DataFrame) -> pd.DataFrame:
    loc_h = d.index.tz_convert(TZ).hour
    night = d[(loc_h >= 23) | (loc_h < 7)]
    if night.empty:
        return pd.DataFrame(columns=["laeq", "la90", "laeq_trim", "coverage", "floor_frac"])
    key = _night_key(night.index)
    rows = {}
    for k, g in night.groupby(key):
        lv = g["laeq"].to_numpy(dtype=float)
        ok = lv[~np.isnan(lv)]
        cov = len(ok) / 480.0
        if cov < MIN_COVERAGE:
            continue
        srt = np.sort(ok)
        trim = srt[: max(int(len(srt) * 0.95), 1)]
        rows[k] = {"laeq": float(db_mean(ok)), "la90": float(np.percentile(ok, 10)),
                   "laeq_trim": float(db_mean(trim)), "coverage": cov}
    df = pd.DataFrame.from_dict(rows, orient="index")
    if df.empty:
        return df
    floor = float(np.nanpercentile(night["laeq"], 1))
    df["floor_est"] = floor
    keys = np.asarray(key)
    df["floor_frac"] = [float(np.mean(night["laeq"][keys == k].dropna() < floor + 2)) for k in df.index]
    return df


def window_open_nights(d: pd.DataFrame, outdoor: pd.Series, noise: pd.DataFrame) -> pd.Series:
    """Heuristic open-window flag per night (True = likely open).

    Open if (a) indoor temperature falls > 0.25 C/h between 23:00 and 05:00 while it is > 3 C warmer
    outside-in, or (b) nightly L_A90 exceeds the room's median nightly L_A90 by > 6 dB."""
    flags = {}
    loc = d.index.tz_convert(TZ)
    keys = _night_key(d.index)
    out_m = outdoor.reindex(d.index, method="nearest", tolerance=pd.Timedelta("1h"))
    med90 = float(noise["la90"].median()) if len(noise) else np.nan
    for k in noise.index:
        sel = (np.asarray(keys) == k) & ((loc.hour >= 23) | (loc.hour < 5))
        g = d.loc[sel, "temp_c"].dropna()
        cooling = False
        if len(g) > 120:
            hrs = (g.index - g.index[0]).total_seconds() / 3600
            slope = float(np.polyfit(hrs, g.to_numpy(), 1)[0])
            dt_io = float(np.nanmean(g.to_numpy() - out_m[sel].reindex(g.index).to_numpy()))
            cooling = slope < -0.25 and dt_io > 3
        loud = noise.loc[k, "la90"] > med90 + 6 if np.isfinite(med90) else False
        flags[k] = bool(cooling or loud)
    return pd.Series(flags, dtype=bool)


def daily_heat(d: pd.DataFrame) -> pd.DataFrame:
    t = d["temp_c"].rolling(10, min_periods=8).mean()
    loc = t.copy()
    loc.index = loc.index.tz_convert(TZ)
    raw = d["temp_c"].copy()
    raw.index = raw.index.tz_convert(TZ)
    g = loc.groupby(loc.index.date)
    cov = raw.groupby(raw.index.date).apply(lambda x: x.notna().mean())
    df = pd.DataFrame({"peak": g.max(), "h_above_26": g.apply(lambda x: float((x > 26).sum()) / 60),
                       "h_above_28": g.apply(lambda x: float((x > 28).sum()) / 60), "coverage": cov})
    return df[df["coverage"] >= MIN_COVERAGE]
