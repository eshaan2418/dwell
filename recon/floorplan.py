"""Point cloud (gravity-aligned, roughly metric) -> 2.5D room geometry: floor/ceiling heights, wall
directions, room rectangle, window openings on walls, and metric scale from known-object cues.

Designed for the rung-2 pipeline (COLMAP sparse / monocular-depth point clouds on CPU). The module is
tested on synthetic scans (recon/synthetic_scan.py) because no real walkthroughs exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DOOR_HEIGHT_M = 2.03  # typical interior door leaf height (2.0-2.1 m); prior sd 0.04 m
DOOR_HEIGHT_SD = 0.04


@dataclass
class RoomEstimate:
    floor_z: float
    ceiling_z: float
    rect: np.ndarray  # (4, 2) corners, counter-clockwise
    wall_dir_deg: float  # dominant wall direction (0-90, compass sense, in the cloud frame)
    windows: list[dict]

    @property
    def area(self) -> float:
        x, y = self.rect[:, 0], self.rect[:, 1]
        return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))

    @property
    def ceiling_height(self) -> float:
        return self.ceiling_z - self.floor_z


def metric_scale(cue_heights: list[float], cue_true: list[float] | None = None) -> tuple[float, float]:
    """Scale factor (metres per cloud unit) from measured heights of known objects (doors by default).

    Returns (scale, relative sd). Combines cues by the median; sd from the prior spread and cue scatter."""
    h = np.asarray(cue_heights, float)
    t = np.asarray(cue_true if cue_true is not None else [DOOR_HEIGHT_M] * len(h), float)
    r = t / h
    s = float(np.median(r))
    rel_sd = float(np.sqrt((DOOR_HEIGHT_SD / DOOR_HEIGHT_M) ** 2 + (np.std(r) / s) ** 2 / max(len(r), 1)))
    return s, rel_sd


def _peaks_z(z: np.ndarray, bin_m: float = 0.03) -> tuple[float, float]:
    lo, hi = np.percentile(z, [0.5, 99.5])
    bins = np.arange(lo - bin_m, hi + 2 * bin_m, bin_m)
    hist, edges = np.histogram(z, bins)
    centres = 0.5 * (edges[:-1] + edges[1:])
    k = max(len(hist) // 4, 1)
    f = centres[np.argmax(hist[:k])]
    c = centres[len(hist) - k + np.argmax(hist[-k:])]
    return float(f), float(c)


def dominant_direction(xy: np.ndarray, k: int = 12) -> float:
    """Manhattan wall direction (deg in [0, 90)) from local PCA normals of wall points (4-fold histogram)."""
    from scipy.spatial import cKDTree

    tree = cKDTree(xy)
    n = min(len(xy), 4000)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(xy), n, replace=False)
    _, nn = tree.query(xy[idx], k=k)
    angs = []
    for row in nn:
        p = xy[row] - xy[row].mean(0)
        _, _, vt = np.linalg.svd(p, full_matrices=False)
        d = vt[0]
        angs.append(np.degrees(np.arctan2(d[0], d[1])) % 90.0)  # compass-sense direction mod 90
    a = np.radians(np.asarray(angs) * 4)  # 4-fold circular mean
    return float((np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())) / 4) % 90.0)


def _rot(xy: np.ndarray, deg: float) -> np.ndarray:
    d = np.radians(deg)
    return np.stack([xy[:, 0] * np.cos(d) - xy[:, 1] * np.sin(d), xy[:, 0] * np.sin(d) + xy[:, 1] * np.cos(d)], 1)


def refine_direction(xy: np.ndarray, d0: float, span: float = 4.0, step: float = 0.1) -> float:
    """Refine the wall direction by minimising the robust (1-99 %) bounding-box area."""
    best, best_a = d0, np.inf
    for d in np.arange(d0 - span, d0 + span + 1e-9, step):
        r = _rot(xy, d)
        lo, hi = np.percentile(r, 1, axis=0), np.percentile(r, 99, axis=0)
        a = float(np.prod(hi - lo))
        if a < best_a:
            best, best_a = d, a
    return float(best % 90.0)


def estimate_room(
    points: np.ndarray, window_min_w: float = 0.75, window_min_h: float = 0.75, cell: float = 0.05
) -> RoomEstimate:
    """points: (N, 3) gravity-aligned metric cloud of one room (z up)."""
    z = points[:, 2]
    fz, cz = _peaks_z(z)
    band = points[(z > fz + 0.3) & (z < cz - 0.3)]
    direction = refine_direction(band[:, :2], dominant_direction(band[:, :2]))
    # rotate into the wall-aligned frame (x', y' axis-aligned walls)
    xy = _rot(band[:, :2], direction)
    lo = np.percentile(xy, 1, axis=0)
    hi = np.percentile(xy, 99, axis=0)
    rect_al = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
    rect = _rot(rect_al, -direction)
    # windows: low-density rectangles on each wall plane (glass returns few points)
    wins = []
    pts_al = np.c_[_rot(points[:, :2], direction), points[:, 2]]
    walls = [("x0", 0, lo[0]), ("x1", 0, hi[0]), ("y0", 1, lo[1]), ("y1", 1, hi[1])]
    for name, axis, pos in walls:
        on = np.abs(pts_al[:, axis] - pos) < 0.08
        other = 1 - axis
        u = pts_al[on, other]
        v = pts_al[on, 2] - fz
        if len(u) < 50:
            continue
        ub = np.arange(lo[other], hi[other] + cell, cell)
        vb = np.arange(0, cz - fz + cell, cell)
        h, _, _ = np.histogram2d(u, v, [ub, vb])
        expected = np.median(h[h > 0]) if (h > 0).any() else 0
        from scipy.ndimage import uniform_filter

        holes = uniform_filter(h, 3) < 0.25 * expected
        # largest connected low-density rectangles: column/row runs
        from scipy.ndimage import label

        lab, n = label(holes)
        for k in range(1, n + 1):
            ii, jj = np.where(lab == k)
            w = (ii.max() - ii.min() + 1) * cell
            hh = (jj.max() - jj.min() + 1) * cell
            fill = len(ii) / ((ii.max() - ii.min() + 1) * (jj.max() - jj.min() + 1))
            if w >= window_min_w and hh >= window_min_h and fill > 0.6 and jj.min() > 0 and jj.max() < h.shape[1] - 1:
                uc = ub[ii.min()] + w / 2
                wins.append(
                    {
                        "wall": name,
                        "width": float(w),
                        "height": float(hh),
                        "sill": float(vb[jj.min()]),
                        "u_centre": float(uc),
                        "wall_pos": float(pos),
                        "axis": axis,
                    }
                )
    return RoomEstimate(fz, cz, rect, direction, wins)
