"""Synthetic phone-scan point clouds of a room (for testing recon/floorplan.py without real videos).

Surfaces are sampled uniformly; window glass returns only a small fraction of points; furniture boxes
add clutter; scan duration controls coverage (unseen wall patches), lighting controls depth noise,
and the capture mode controls the unknown global scale (plain video) vs metric AR poses.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.scene import Room, Window

QUALITY = {
    "short_60s": {"coverage": 0.70, "density": 250.0},
    "nominal_120s": {"coverage": 0.88, "density": 400.0},
    "long_240s": {"coverage": 0.96, "density": 600.0},
}
LIGHT = {"good": 0.012, "dim": 0.035}


@dataclass
class ScanConfig:
    duration: str = "nominal_120s"
    lighting: str = "good"
    metric_ar: bool = False  # AR poses give metric scale (scale error ~1 %)


def _plane(rng, origin, u, v, lu, lv, density):
    n = int(lu * lv * density)
    a, b = rng.random(n) * lu, rng.random(n) * lv
    return origin[None, :] + a[:, None] * u[None, :] + b[:, None] * v[None, :], a, b


def scan_room(rng: np.random.Generator, room: Room, windows: list[Window], cfg: ScanConfig) -> dict:
    q = QUALITY[cfg.duration]
    sigma = LIGHT[cfg.lighting]
    poly = np.asarray(room.polygon, float)
    fz, h = room.floor_z, room.ceiling_height
    pts = []
    x0, y0 = poly.min(0)
    x1, y1 = poly.max(0)
    # floor / ceiling (sample bounding box, keep inside polygon)
    from shapely.geometry import Polygon

    pg = Polygon(poly)
    for z in (fz, fz + h):
        n = int(pg.area * q["density"])
        xy = np.c_[rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)]
        import shapely

        xy = xy[shapely.contains_xy(pg, xy[:, 0], xy[:, 1])]
        pts.append(np.c_[xy, np.full(len(xy), z)])
    # walls
    for a, b in zip(poly, np.roll(poly, -1, axis=0), strict=True):
        d = b - a
        L = float(np.linalg.norm(d))
        u = np.r_[d / L, 0.0]
        P, s, t = _plane(rng, np.r_[a, fz], u, np.array([0, 0, 1.0]), L, h, q["density"])
        keep = np.ones(len(P), bool)
        for w in windows:
            # window on this wall if its centre is within 5 cm of the wall line
            c = np.array([w.cx, w.cy])
            proj = np.dot(c - a, d / L)
            dist = np.linalg.norm(c - (a + proj * d / L))
            if dist < 0.6 and 0 <= proj <= L:
                inside = (np.abs(s - proj) < w.width / 2) & (t > w.sill_z - fz) & (t < w.sill_z - fz + w.height)
                keep &= ~inside | (rng.random(len(P)) < 0.05)
        # coverage holes: drop random 0.6 m patches
        n_holes = int((1 - q["coverage"]) * L * h / 0.36)
        for _ in range(n_holes):
            cs, ct = rng.uniform(0, L), rng.uniform(0, h)
            keep &= ~((np.abs(s - cs) < 0.3) & (np.abs(t - ct) < 0.3))
        pts.append(P[keep])
    # furniture clutter boxes along walls
    import shapely

    inner = pg.buffer(-0.3)
    for _ in range(int(rng.integers(2, 5))):
        sz = rng.uniform(0.4, 1.2, 3) * np.array([1, 1, 0.9])
        n = int(sz[0] * sz[1] * 2 * q["density"])
        cx, cy = rng.uniform(x0, x1), rng.uniform(y0, y1)
        fx = np.c_[rng.uniform(cx - sz[0] / 2, cx + sz[0] / 2, n), rng.uniform(cy - sz[1] / 2, cy + sz[1] / 2, n)]
        fx = fx[shapely.contains_xy(inner, fx[:, 0], fx[:, 1])]  # furniture stays inside the room
        pts.append(np.c_[fx, fz + rng.uniform(0, sz[2], len(fx))])
    cloud = np.concatenate(pts)
    cloud = cloud + rng.normal(0, sigma, cloud.shape)
    # unknown global scale (plain video SfM) or ~1 % (AR)
    scale_true = 1.0 if cfg.metric_ar else float(rng.uniform(0.3, 3.0))
    if cfg.metric_ar:
        scale_true = float(rng.normal(1.0, 0.01))
    cloud_scaled = cloud / scale_true
    door_h_measured = float((2.03 + rng.normal(0, 0.04)) / scale_true + rng.normal(0, 2 * sigma) / scale_true)
    return {"points": cloud_scaled, "scale_true": scale_true, "door_heights": [door_h_measured]}
