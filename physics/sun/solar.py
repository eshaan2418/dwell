"""Solar position.

Primary: NREL SPA (Reda & Andreas 2004/2008) via ``pvlib.solarposition.spa_python``.
Secondary: a compact NOAA-style implementation (used for a cross-check test and when
pvlib is unavailable). Azimuth convention everywhere in Dwell: degrees clockwise from
geographic north; elevation in degrees above the horizon.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TORONTO = {"lat": 43.6532, "lon": -79.3832, "elev": 76.0, "tz": "America/Toronto"}


def solar_position(
    times: pd.DatetimeIndex,
    lat: float,
    lon: float,
    elev: float = 0.0,
    pressure_hpa: float = 1013.25,
    temp_c: float = 12.0,
) -> pd.DataFrame:
    """Apparent solar elevation/azimuth (deg) using NREL SPA through pvlib."""
    import pvlib

    if times.tz is None:
        raise ValueError("times must be timezone-aware")
    sp = pvlib.solarposition.spa_python(
        times, lat, lon, altitude=elev, pressure=pressure_hpa * 100.0, temperature=temp_c
    )
    return pd.DataFrame(
        {
            "elevation": sp["apparent_elevation"].to_numpy(),
            "azimuth": sp["azimuth"].to_numpy(),
            "zenith": sp["apparent_zenith"].to_numpy(),
        },
        index=times,
    )


def noaa_solar_position(times: pd.DatetimeIndex, lat: float, lon: float) -> pd.DataFrame:
    """NOAA solar calculator equations (Meeus-based, ~0.01–0.05 deg). No refraction."""
    t_utc = times.tz_convert("UTC")
    jd = t_utc.to_julian_date().to_numpy()
    jc = (jd - 2451545.0) / 36525.0
    l0 = np.mod(280.46646 + jc * (36000.76983 + jc * 0.0003032), 360.0)
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = np.radians(m)
    c = (
        np.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + np.sin(2 * mr) * (0.019993 - 0.000101 * jc)
        + np.sin(3 * mr) * 0.000289
    )
    true_long = l0 + c
    omega = 125.04 - 1934.136 * jc
    app_long = true_long - 0.00569 - 0.00478 * np.sin(np.radians(omega))
    eps0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * np.cos(np.radians(omega))
    decl = np.degrees(np.arcsin(np.sin(np.radians(eps)) * np.sin(np.radians(app_long))))
    y = np.tan(np.radians(eps / 2)) ** 2
    l0r = np.radians(l0)
    eot = 4 * np.degrees(
        y * np.sin(2 * l0r)
        - 2 * e * np.sin(mr)
        + 4 * e * y * np.sin(mr) * np.cos(2 * l0r)
        - 0.5 * y * y * np.sin(4 * l0r)
        - 1.25 * e * e * np.sin(2 * mr)
    )
    minutes = t_utc.hour * 60 + t_utc.minute + t_utc.second / 60
    tst = np.mod(minutes.to_numpy() + eot + 4 * lon, 1440)
    ha = np.where(tst / 4 < 0, tst / 4 + 180, tst / 4 - 180)
    latr, declr, har = np.radians(lat), np.radians(decl), np.radians(ha)
    cosz = np.sin(latr) * np.sin(declr) + np.cos(latr) * np.cos(declr) * np.cos(har)
    zen = np.degrees(np.arccos(np.clip(cosz, -1, 1)))
    az_num = np.sin(latr) * np.cos(np.radians(zen)) - np.sin(declr)
    az_den = np.cos(latr) * np.sin(np.radians(zen))
    with np.errstate(invalid="ignore", divide="ignore"):
        az_c = np.degrees(np.arccos(np.clip(az_num / az_den, -1, 1)))
    az = np.where(ha > 0, np.mod(az_c + 180, 360), np.mod(540 - az_c, 360))
    return pd.DataFrame({"elevation": 90 - zen, "azimuth": az, "zenith": zen}, index=times)


def sun_vector(azimuth_deg: np.ndarray, elevation_deg: np.ndarray) -> np.ndarray:
    """Unit vector pointing *towards* the sun in local ENU (x=east, y=north, z=up)."""
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    return np.stack([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)], axis=-1)


def clear_sky(times: pd.DatetimeIndex, lat: float, lon: float, elev: float = 76.0) -> pd.DataFrame:
    """Ineichen–Perez clear-sky GHI/DNI/DHI [W/m2] (pvlib, climatological Linke turbidity)."""
    import pvlib

    loc = pvlib.location.Location(lat, lon, altitude=elev)
    try:
        cs = loc.get_clearsky(times, model="ineichen")
    except Exception:  # Linke turbidity file unavailable -> simple model
        cs = loc.get_clearsky(times, model="haurwitz")
        cs["dni"] = np.nan
        cs["dhi"] = np.nan
    return cs
