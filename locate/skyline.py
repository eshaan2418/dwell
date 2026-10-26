"""Horizon (skyline) elevation from a window-view frame, for validating the geodata horizon profile.

Given an image (H, W, 3) taken looking out of a window with known camera yaw (azimuth of the optical
axis), pitch and horizontal field of view, segment the sky (bright, low-saturation-or-blue, connected to
the top edge) and convert the lowest sky pixel per column into an elevation angle (pinhole model).
"""

from __future__ import annotations

import numpy as np


def sky_mask(img: np.ndarray, thresh: float | None = None) -> np.ndarray:
    x = img.astype(float) / 255.0
    lum = x.mean(axis=2)
    blue = x[..., 2] - 0.5 * (x[..., 0] + x[..., 1])
    score = lum + 0.5 * np.clip(blue, 0, None)
    t = thresh if thresh is not None else float(np.percentile(score, 60))
    m = score > t
    # keep only pixels connected to the top edge
    from scipy.ndimage import label

    lab, _ = label(m)
    top = set(np.unique(lab[0][lab[0] > 0]).tolist())
    return np.isin(lab, list(top))


def skyline_elevation(
    img: np.ndarray, yaw_deg: float, pitch_deg: float, hfov_deg: float, mask: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return (azimuths, elevations) per image column (NaN where the column has no sky)."""
    h, w = img.shape[:2]
    m = sky_mask(img) if mask is None else mask
    f = (w / 2) / np.tan(np.radians(hfov_deg) / 2)
    cols = np.arange(w)
    xs = cols - (w - 1) / 2
    az = (yaw_deg + np.degrees(np.arctan2(xs, f))) % 360
    el = np.full(w, np.nan)
    for c in cols:
        rows = np.where(m[:, c])[0]
        if len(rows) == 0:
            continue
        r = rows.max() + 0.5  # lowest sky pixel = skyline
        ys = (h - 1) / 2 - r
        # elevation of the ray through (xs, ys) for a camera pitched by pitch_deg
        d = np.array([xs[c], f, ys])
        cp, sp = np.cos(np.radians(pitch_deg)), np.sin(np.radians(pitch_deg))
        y2, z2 = d[1] * cp - d[2] * sp, d[1] * sp + d[2] * cp
        el[c] = np.degrees(np.arctan2(z2, np.hypot(d[0], y2)))
    return az, el


def render_skyline(
    h_profile_az: np.ndarray,
    h_profile_el: np.ndarray,
    yaw_deg: float,
    pitch_deg: float,
    hfov_deg: float,
    shape: tuple[int, int] = (240, 320),
) -> np.ndarray:
    """Render a synthetic view (sky = bright blue above the horizon profile) for testing."""
    h, w = shape
    f = (w / 2) / np.tan(np.radians(hfov_deg) / 2)
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (70, 70, 70)
    cp, sp = np.cos(np.radians(pitch_deg)), np.sin(np.radians(pitch_deg))
    for c in range(w):
        xs = c - (w - 1) / 2
        az = (yaw_deg + np.degrees(np.arctan2(xs, f))) % 360
        hel = np.interp(az, h_profile_az, h_profile_el, period=360)
        for r in range(h):
            ys = (h - 1) / 2 - (r + 0.5)
            y2, z2 = f * cp - ys * sp, f * sp + ys * cp
            el = np.degrees(np.arctan2(z2, np.hypot(xs, y2)))
            if el > max(hel, -89):
                img[r, c] = (150, 190, 240)
    return img
