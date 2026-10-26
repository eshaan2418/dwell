"""Obstruction model: neighbouring buildings (extruded footprints) and trees.

``horizon_profile`` returns, for a viewpoint, the elevation angle of the opaque skyline
for each azimuth bin. For an extruded prism of constant height the maximum elevation along a
ray is attained at the nearest boundary crossing, so the profile is exact for prisms (up to
azimuth discretisation).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.scene import Building, Tree

AZ_STEP = 0.5
AZ_GRID = np.arange(0.0, 360.0, AZ_STEP)


@dataclass
class Horizon:
    az: np.ndarray  # deg
    elevation: np.ndarray  # deg, -90 where no obstruction

    def at(self, az_deg: np.ndarray) -> np.ndarray:
        idx = np.round(np.mod(az_deg, 360.0) / AZ_STEP).astype(int) % len(self.az)
        return self.elevation[idx]


def _segments(buildings: list[Building]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p1, p2, h = [], [], []
    for b in buildings:
        fp = list(b.footprint)
        for a, c in zip(fp, fp[1:] + fp[:1], strict=True):
            p1.append(a)
            p2.append(c)
            h.append(b.height)
    if not p1:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0)
    return np.asarray(p1, float), np.asarray(p2, float), np.asarray(h, float)


def ray_hits(px: float, py: float, az_deg: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """Distances t (A x N) along rays to each segment; inf where no hit."""
    a = np.radians(az_deg)[:, None]
    dx, dy = np.sin(a), np.cos(a)
    ex, ey = (p2 - p1)[:, 0][None, :], (p2 - p1)[:, 1][None, :]
    wx, wy = (p1[:, 0] - px)[None, :], (p1[:, 1] - py)[None, :]
    denom = dx * ey - dy * ex
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (wx * ey - wy * ex) / denom
        u = (wx * dy - wy * dx) / denom
    ok = (np.abs(denom) > 1e-12) & (t > 1e-6) & (u >= 0) & (u <= 1)
    return np.where(ok, t, np.inf)


def horizon_profile(
    x: float,
    y: float,
    z: float,
    buildings: list[Building],
    az_grid: np.ndarray = AZ_GRID,
    max_dist: float = 2000.0,
) -> Horizon:
    p1, p2, h = _segments(buildings)
    if len(h) == 0:
        return Horizon(az_grid, np.full(len(az_grid), -90.0))
    t = ray_hits(x, y, az_grid, p1, p2)
    t = np.where(t <= max_dist, t, np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        el = np.degrees(np.arctan2(h[None, :] - z, t))
    el = np.where(np.isfinite(t), el, -90.0)
    return Horizon(az_grid, el.max(axis=1))


def tree_transmittance(
    x: float,
    y: float,
    z: float,
    sun_az: np.ndarray,
    sun_el: np.ndarray,
    trees: list[Tree],
    leaf_on: np.ndarray,
) -> np.ndarray:
    """Fraction of direct beam transmitted through tree canopies (vertical-cylinder canopies)."""
    trans = np.ones_like(sun_az, dtype=float)
    if not trees:
        return trans
    a = np.radians(sun_az)
    dx, dy = np.sin(a), np.cos(a)
    tan_el = np.tan(np.radians(np.clip(sun_el, 0.1, 89.9)))
    for tr in trees:
        ox, oy = tr.x - x, tr.y - y
        proj = ox * dx + oy * dy  # horizontal distance along ray to closest approach
        perp2 = ox * ox + oy * oy - proj * proj
        hit = (perp2 < tr.radius**2) & (proj > 0)
        half = np.sqrt(np.clip(tr.radius**2 - perp2, 0, None))
        t_in, t_out = np.clip(proj - half, 0, None), proj + half
        z_in, z_out = z + t_in * tan_el, z + t_out * tan_el
        through = hit & (z_in < tr.height) & (z_out > tr.trunk_height)
        por = np.where(leaf_on, tr.porosity_leaf_on, tr.porosity_leaf_off)
        trans = np.where(through, trans * por, trans)
    return trans


def leaf_on_mask(month: np.ndarray) -> np.ndarray:
    """Toronto deciduous canopy: leaf-on mid-May .. late Oct (approximated by months 5-10)."""
    return (month >= 5) & (month <= 10)


def vertical_sky_view_factor(h: Horizon, facade_az: float) -> float:
    """View factor from a vertical surface to the visible sky (0.5 when unobstructed).

    F = (1/pi) * Int_{-pi/2}^{pi/2} cos(phi) * [pi/4 - h/2 - sin(2h)/4] dphi, with h(phi) >= 0.
    """
    rel = np.radians(((h.az - facade_az + 180) % 360) - 180)
    front = np.abs(rel) < np.pi / 2
    hh = np.radians(np.clip(h.elevation, 0, 90))
    integrand = np.cos(rel) * (np.pi / 4 - hh / 2 - np.sin(2 * hh) / 4)
    dphi = np.radians(AZ_STEP if len(h.az) == len(AZ_GRID) else 360.0 / len(h.az))
    return float(np.sum(integrand[front]) * dphi / np.pi)
