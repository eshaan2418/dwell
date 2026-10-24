"""Facade sound insulation and indoor level.

Band sound reduction indices R (125 Hz-4 kHz octaves) for glazing are typical published-range
values for common constructions (approximate engineering values, not product data). Opaque walls
use the field-incidence mass law, R = 20 log10(m f) - 47 dB, capped for flanking; light timber
frame walls use a typical band curve. Frame leakage is an equivalent open slit area with
transmission coefficient 1 (frequency independent).

Indoor level (diffuse field in the receiving room):
    L_in = L_inc - R_comp + 10 log10(S / A) + C_inc
with L_inc the free-field incident level at the facade, S the exposed facade area, A the room
absorption area (Sabine, A = 0.161 V / T60), and C_inc an incidence correction between 0 dB
(diffuse incidence) and 6 dB (normal plane-wave incidence); default 3 dB, treated as uncertain.
"""

from __future__ import annotations

import numpy as np

from physics.acoustics.levels import OCTAVES

GLAZING_R = {
    "single": np.array([20.0, 22.0, 27.0, 31.0, 32.0, 28.0]),
    "double": np.array([23.0, 20.0, 27.0, 36.0, 40.0, 36.0]),
    "double_lowe": np.array([24.0, 23.0, 31.0, 39.0, 40.0, 42.0]),
    "triple": np.array([25.0, 25.0, 31.0, 38.0, 43.0, 44.0]),
}
LEAK_FRACTION = {"tight": 2e-5, "average": 2e-4, "leaky": 2e-3}  # slit area / window area
WALL_MASS = {"light_frame": None, "masonry": 250.0, "concrete": 400.0}  # kg/m2
LIGHT_FRAME_R = np.array([28.0, 36.0, 43.0, 48.0, 51.0, 54.0])
FRAME_R = np.array([25.0, 28.0, 32.0, 35.0, 37.0, 38.0])  # frame profiles
R_CAP = 60.0
T60_BY_FURNISHING = {"sparse": 0.8, "typical": 0.5, "heavy": 0.35}


def mass_law(m_kg_m2: float, f: np.ndarray = OCTAVES) -> np.ndarray:
    return np.minimum(20 * np.log10(m_kg_m2 * f) - 47.0, R_CAP)


def wall_r(wall_type: str) -> np.ndarray:
    m = WALL_MASS[wall_type]
    return LIGHT_FRAME_R.copy() if m is None else mass_law(m)


def tau(r_db: np.ndarray) -> np.ndarray:
    return 10 ** (-np.asarray(r_db) / 10)


def composite_r(elements: list[tuple[float, np.ndarray]], leak_area: float = 0.0) -> np.ndarray:
    """Composite R from (area, R-band) pairs plus an open leak/aperture area (tau = 1)."""
    s_tot = sum(a for a, _ in elements) + 0.0
    t = sum(a * tau(r) for a, r in elements) + leak_area
    return -10 * np.log10(t / s_tot)


def facade_r(
    wall_area: float, wall_type: str, windows: list[tuple[float, str, str, float]],
    open_area: float = 0.0,
) -> np.ndarray:
    """Composite R of a room facade.

    windows: list of (window area, glazing, frame, frame_fraction). ``open_area`` is the free
    opening area when windows are ajar (m2)."""
    win_area = sum(a for a, *_ in windows)
    elems: list[tuple[float, np.ndarray]] = [(max(wall_area - win_area, 0.1), wall_r(wall_type))]
    leak = 0.0
    for a, glazing, frame, ff in windows:
        elems.append((a * (1 - ff), GLAZING_R[glazing]))
        elems.append((a * ff, FRAME_R))
        leak += a * LEAK_FRACTION[frame]
    return composite_r(elems, leak + open_area)


def absorption_area(volume_m3: float, furnishing: str) -> float:
    return 0.161 * volume_m3 / T60_BY_FURNISHING[furnishing]


def indoor_level(l_inc_band: np.ndarray, r_band: np.ndarray, facade_area: float, a_abs: float,
                 c_inc: float = 3.0) -> np.ndarray:
    """Indoor band levels from incident band levels (any leading shape, last axis = bands)."""
    return l_inc_band - r_band + 10 * np.log10(facade_area / a_abs) + c_inc
