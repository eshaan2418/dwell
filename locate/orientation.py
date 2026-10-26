"""Window/facade orientation: fuse phone compass, reconstruction wall direction, and footprint edges.

The reconstruction gives the wall direction only modulo 90 deg (Manhattan rooms) in an arbitrary
frame; the phone compass (indoors, magnetic disturbance) gives an absolute but noisy azimuth; the
building footprint (OSM / Toronto massing) gives exact absolute edge directions. Strategy:
  1. coarse absolute azimuth = compass (+ magnetic declination for Toronto);
  2. snap to the nearest outward normal of the footprint edges whose normal lies within +-30 deg;
  3. if no edge qualifies, use compass corrected by the recon wall direction mod 90.
"""

from __future__ import annotations

import numpy as np

TORONTO_DECLINATION_DEG = -9.9  # magnetic declination (west negative), approx. 2026 (NOAA WMM); D-016


def edge_normals(footprint: list[tuple[float, float]]) -> np.ndarray:
    """Outward normal azimuths (deg) of polygon edges (polygon CCW or CW handled)."""
    p = np.asarray(footprint, float)
    q = np.roll(p, -1, axis=0)
    area2 = np.sum(p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1])
    d = q - p
    # outward normal for CCW polygon is (dy, -dx)
    nx, ny = (d[:, 1], -d[:, 0]) if area2 > 0 else (-d[:, 1], d[:, 0])
    return np.degrees(np.arctan2(nx, ny)) % 360


def angdiff(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    return (np.asarray(a) - np.asarray(b) + 180) % 360 - 180


def fuse(
    compass_mag_deg: float,
    footprint: list[tuple[float, float]] | None,
    recon_dir_mod90: float | None = None,
    snap_window: float = 30.0,
    declination: float = TORONTO_DECLINATION_DEG,
) -> dict:
    true_compass = (compass_mag_deg + declination) % 360
    if footprint:
        normals = edge_normals(footprint)
        d = np.abs(angdiff(normals, true_compass))
        k = int(np.argmin(d))
        if d[k] <= snap_window:
            return {"azimuth": float(normals[k]), "method": "footprint_snap", "residual_deg": float(d[k])}
    if recon_dir_mod90 is not None:
        cands = (recon_dir_mod90 + np.arange(4) * 90) % 360
        k = int(np.argmin(np.abs(angdiff(cands, true_compass))))
        return {
            "azimuth": float(cands[k]),
            "method": "compass+recon",
            "residual_deg": float(abs(angdiff(cands[k], true_compass))),
        }
    return {"azimuth": float(true_compass), "method": "compass", "residual_deg": 0.0}
