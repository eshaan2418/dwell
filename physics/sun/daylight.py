"""Window -> room direct sun, sun patches and a diffuse-daylight estimate.

Window-local coordinates on the glass plane: u = lateral (m, +right looking out),
v = height above the sill (m). The glass sits ``reveal_depth`` behind the outer wall face.
The sunlit aperture on the glass plane, accounting for the outer reveal and an overhang /
balcony above, is an axis-aligned rectangle in (u, v) and is computed in closed form.
Neighbouring buildings (horizon profile) and trees act on the whole window.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from core.scene import Unit, Window
from physics.sun.obstruction import Horizon, horizon_profile, leaf_on_mask, tree_transmittance
from physics.sun.solar import solar_position, sun_vector

SENSOR_DEPTH_BEHIND_GLASS = 0.08  # placement guide: kit on the sill, 8 cm behind the glass
SENSOR_HEIGHT_ABOVE_SILL = 0.03


def window_frame(w: Window) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(glass-plane centre at sill height, outward normal n, lateral tangent t)."""
    az = np.radians(w.azimuth)
    n = np.array([np.sin(az), np.cos(az), 0.0])
    t = np.array([np.cos(az), -np.sin(az), 0.0])
    c = np.array([w.cx, w.cy, w.sill_z]) - n * w.reveal_depth
    return c, n, t


def aperture(w: Window, s: np.ndarray) -> np.ndarray:
    """Sunlit aperture rectangles on the glass plane, shape (T, 4) = u0, u1, v0, v1 (empty if u1<=u0)."""
    _, n, t = window_frame(w)
    s_n = s @ n
    s_t = s @ t
    s_z = s[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        tau = np.where(s_n > 1e-6, w.reveal_depth / s_n, np.inf)
        u0 = np.maximum(-w.width / 2, -w.width / 2 - tau * s_t)
        u1 = np.minimum(w.width / 2, w.width / 2 - tau * s_t)
        v0 = np.maximum(0.0, -tau * s_z)
        v1 = np.minimum(w.height, w.height - tau * s_z)
        if w.overhang_depth > 0:
            v1 = np.minimum(v1, w.height + w.overhang_gap - w.overhang_depth * s_z / s_n - tau * s_z)
    rect = np.stack([u0, u1, v0, v1], axis=1)
    bad = (s_n <= 1e-6) | (s_z <= 0) | ~np.isfinite(rect).all(axis=1)
    rect[bad] = [0, 0, 0, 0]
    return rect


def rect_area(rect: np.ndarray) -> np.ndarray:
    return np.clip(rect[:, 1] - rect[:, 0], 0, None) * np.clip(rect[:, 3] - rect[:, 2], 0, None)


@dataclass
class WindowContext:
    window: Window
    horizon: Horizon


def window_contexts(unit: Unit, include_trees_in_horizon: bool = False) -> list[WindowContext]:
    out = []
    for w in unit.windows:
        az = np.radians(w.azimuth)
        x = w.cx + 0.02 * np.sin(az)
        y = w.cy + 0.02 * np.cos(az)
        z = w.sill_z + w.height / 2
        out.append(WindowContext(w, horizon_profile(x, y, z, unit.context_buildings)))
    return out


def sun_on_windows(
    unit: Unit,
    times: pd.DatetimeIndex,
    contexts: list[WindowContext] | None = None,
    use_trees: bool = True,
    solpos: pd.DataFrame | None = None,
    sensor_offsets: dict[str, tuple[float, float]] | None = None,
) -> dict[str, pd.DataFrame]:
    """Per window: sunlit glazing area [m2], sunlit fraction, sensor-point sunlit flag (if room sensor
    sits on this window's sill), and the beam obstruction factor (horizon x trees)."""
    contexts = contexts or window_contexts(unit)
    sp = solpos if solpos is not None else solar_position(times, unit.lat, unit.lon)
    s = sun_vector(sp["azimuth"].to_numpy(), sp["elevation"].to_numpy())
    up = sp["elevation"].to_numpy() > 0
    leaf = leaf_on_mask(times.month.to_numpy())
    out: dict[str, pd.DataFrame] = {}
    for ctx in contexts:
        w = ctx.window
        rect = aperture(w, s)
        visible = up & (sp["elevation"].to_numpy() > ctx.horizon.at(sp["azimuth"].to_numpy()))
        trans = np.ones(len(times))
        if use_trees and unit.trees:
            trans = tree_transmittance(
                w.cx,
                w.cy,
                w.sill_z + w.height / 2,
                sp["azimuth"].to_numpy(),
                sp["elevation"].to_numpy(),
                unit.trees,
                leaf,
            )
        beam = visible * trans
        area = rect_area(rect) * beam
        # sensor point on the sill: ray to glass plane must land inside the aperture
        _, n, t = window_frame(w)
        s_n = s @ n
        du, depth = (sensor_offsets or {}).get(w.id, (0.0, SENSOR_DEPTH_BEHIND_GLASS))
        with np.errstate(divide="ignore", invalid="ignore"):
            tau_g = depth / s_n
        us = du + tau_g * (s @ t)
        vs = SENSOR_HEIGHT_ABOVE_SILL + tau_g * s[:, 2]
        in_ap = (us > rect[:, 0]) & (us < rect[:, 1]) & (vs > rect[:, 2]) & (vs < rect[:, 3]) & (s_n > 1e-6)
        out[w.id] = pd.DataFrame(
            {
                "sunlit_area": area,
                "sunlit_frac": area / (w.width * w.height),
                "sensor_beam": np.where(in_ap, beam, 0.0),
                "beam_factor": beam,
                "sun_el": sp["elevation"].to_numpy(),
                "sun_az": sp["azimuth"].to_numpy(),
            },
            index=times,
        )
    return out


def sensor_window(unit: Unit, room_id: str) -> Window | None:
    """The window whose sill holds the room's light sensor (placement guide: main window)."""
    room = unit.room(room_id)
    wins = unit.windows_of(room_id)
    if not wins:
        return None
    if room.sensor_xyz is None:
        return max(wins, key=lambda w: w.width * w.height)
    sx, sy, _ = room.sensor_xyz
    return min(wins, key=lambda w: (w.cx - sx) ** 2 + (w.cy - sy) ** 2)


def room_sun_timeseries(
    unit: Unit, times: pd.DatetimeIndex, per_window: dict[str, pd.DataFrame], min_area_m2: float = 0.1
) -> dict[str, pd.DataFrame]:
    out = {}
    for r in unit.rooms:
        wins = unit.windows_of(r.id)
        area = sum((per_window[w.id]["sunlit_area"] for w in wins), start=pd.Series(0.0, index=times))
        sw = sensor_window(unit, r.id)
        sensor = per_window[sw.id]["sensor_beam"] if sw is not None else pd.Series(0.0, index=times)
        out[r.id] = pd.DataFrame(
            {
                "sunlit_area": area,
                "room_sun": (area >= min_area_m2).astype(float),
                "sensor_sun": (sensor > 0.5).astype(float),
            },
            index=times,
        )
    return out


def daily_sun_hours(ts: pd.DataFrame, p_sun: pd.Series | None, step_h: float, tz: str) -> pd.DataFrame:
    """Expected direct-sun hours per local day for room and sensor point.

    ``p_sun`` is the probability that the sun disc is unobscured by cloud at each time step
    (1.0 = clear-sky potential)."""
    p = p_sun.reindex(ts.index).fillna(0.0) if p_sun is not None else 1.0
    df = pd.DataFrame(
        {"room_h": ts["room_sun"] * p * step_h, "sensor_h": ts["sensor_sun"] * p * step_h}, index=ts.index
    )
    return df.groupby(df.index.tz_convert(tz).date).sum()


def sun_patch_polygon(unit: Unit, w: Window, sun_az: float, sun_el: float) -> Polygon | None:
    """Floor sun patch (shapely polygon, ENU xy) from one window at one sun position, clipped to its room."""
    s = sun_vector(np.array([sun_az]), np.array([sun_el]))
    rect = aperture(w, s)[0]
    if rect[1] <= rect[0] or rect[3] <= rect[2]:
        return None
    c, _, t = window_frame(w)
    room = unit.room(w.room_id)
    pts = []
    for u, v in [(rect[0], rect[2]), (rect[1], rect[2]), (rect[1], rect[3]), (rect[0], rect[3])]:
        g = c + t * u + np.array([0, 0, v])
        k = (g[2] - room.floor_z) / s[0, 2]
        p = g - s[0] * k
        pts.append((p[0], p[1]))
    patch = Polygon(pts)
    if not patch.is_valid or patch.area < 1e-6:
        return None
    clipped = patch.intersection(Polygon(room.polygon))
    return clipped if clipped.area > 1e-4 else None


def average_daylight_factor(
    unit: Unit, room_id: str, contexts: list[WindowContext], tau_vis: float = 0.7, r_mean: float = 0.5
) -> float:
    """BRE average daylight factor (%), ADF = T * Aw * theta / (A * (1 - R^2)), theta = visible sky angle.

    theta (deg) is derived from the vertical sky view factor: unobstructed vertical window -> 90 deg.
    """
    from physics.sun.obstruction import vertical_sky_view_factor

    room = unit.room(room_id)
    poly = Polygon(room.polygon)
    a_total = 2 * poly.area + poly.length * room.ceiling_height
    s = 0.0
    for ctx in contexts:
        if ctx.window.room_id != room_id:
            continue
        w = ctx.window
        theta = 90.0 * vertical_sky_view_factor(ctx.horizon, w.azimuth) / 0.5
        s += tau_vis * w.width * w.height * (1 - w.frame_fraction) * theta
    return float(s / (a_total * (1 - r_mean**2)))
