"""ISO 13790:2008 simple hourly method (5R1C), free-floating with optional heating/cooling.

Node temperatures: theta_air (air), theta_s (central/surface), theta_m (mass). Equations follow
ISO 13790 Annex C (C.1-C.11); Crank-Nicolson update of the mass node with 1 h steps.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

H_IS = 3.45  # W/m2K, coupling air-surface per m2 of A_t
H_MS = 9.1  # W/m2K, coupling surface-mass per m2 of A_m
RHO_CP_AIR = 1200.0  # J/m3K

# ISO 13790 Table 12 (A_m factor x A_f, C_m per m2 A_f in J/K)
MASS_CLASSES = {
    "very_light": (2.5, 80e3), "light": (2.5, 110e3), "medium": (2.5, 165e3),
    "heavy": (3.0, 260e3), "very_heavy": (3.5, 370e3),
}


@dataclass
class RCParams:
    floor_area: float  # A_f, m2
    h_tr_w: float  # windows (and other zero-mass elements), W/K
    h_tr_op: float  # opaque exterior elements, W/K
    mass_class: str = "medium"
    heat_setpoint: float | None = None  # C (None = free-floating)
    cool_setpoint: float | None = None
    max_cool_w_m2: float = 60.0
    max_heat_w_m2: float = 100.0

    @property
    def a_t(self) -> float:
        return 4.5 * self.floor_area

    @property
    def a_m(self) -> float:
        return MASS_CLASSES[self.mass_class][0] * self.floor_area

    @property
    def c_m(self) -> float:
        return MASS_CLASSES[self.mass_class][1] * self.floor_area


def simulate(p: RCParams, theta_e: np.ndarray, h_ve: np.ndarray, phi_int: np.ndarray,
             phi_sol: np.ndarray, theta_m0: float | None = None, h_party: float = 0.0,
             theta_party: float = 22.0) -> dict[str, np.ndarray]:
    """Hourly simulation. All inputs are per-hour arrays (h_ve in W/K). Returns node temps and HC power.

    ``h_party`` (W/K) optionally couples the air node to neighbouring units at ``theta_party`` using the
    previous step's air temperature (explicit; used by the synthetic ground-truth simulator)."""
    n = len(theta_e)
    h_tr_is = H_IS * p.a_t
    h_tr_ms = H_MS * p.a_m
    h_tr_em = 1.0 / (1.0 / p.h_tr_op - 1.0 / h_tr_ms) if p.h_tr_op > 0 else 1e-9
    a_t, a_m, c_m = p.a_t, p.a_m, p.c_m
    tm_prev = float(theta_e[0] if theta_m0 is None else theta_m0)
    t_air = np.empty(n)
    t_s = np.empty(n)
    t_m = np.empty(n)
    phi_hc = np.zeros(n)

    ta_prev = float(theta_e[0] if theta_m0 is None else theta_m0)

    def step(i: int, hc: float, tm_prev: float) -> tuple[float, float, float, float]:
        hc = hc + h_party * (theta_party - ta_prev)
        hve = max(h_ve[i], 1e-6)
        te = theta_e[i]
        t_sup = te
        h1 = 1.0 / (1.0 / hve + 1.0 / h_tr_is)
        h2 = h1 + p.h_tr_w
        h3 = 1.0 / (1.0 / h2 + 1.0 / h_tr_ms)
        phi_ia = 0.5 * phi_int[i]
        phi_m = a_m / a_t * (0.5 * phi_int[i] + phi_sol[i])
        phi_st = (1 - a_m / a_t - p.h_tr_w / (9.1 * a_t)) * (0.5 * phi_int[i] + phi_sol[i])
        phi_mtot = phi_m + h_tr_em * te + h3 * (phi_st + p.h_tr_w * te + h1 * ((phi_ia + hc) / hve + t_sup)) / h2
        k = c_m / 3600.0
        tm_t = (tm_prev * (k - 0.5 * (h3 + h_tr_em)) + phi_mtot) / (k + 0.5 * (h3 + h_tr_em))
        tm = 0.5 * (tm_t + tm_prev)
        ts = (h_tr_ms * tm + phi_st + p.h_tr_w * te + h1 * (t_sup + (phi_ia + hc) / hve)) / (h_tr_ms + p.h_tr_w + h1)
        ta = (h_tr_is * ts + hve * t_sup + phi_ia + hc) / (h_tr_is + hve)
        return ta, ts, tm, tm_t

    for i in range(n):
        ta, ts, tm, tm_t = step(i, 0.0, tm_prev)
        hc = 0.0
        target = None
        if p.cool_setpoint is not None and ta > p.cool_setpoint:
            target, cap = p.cool_setpoint, -p.max_cool_w_m2 * p.floor_area
        elif p.heat_setpoint is not None and ta < p.heat_setpoint:
            target, cap = p.heat_setpoint, p.max_heat_w_m2 * p.floor_area
        if target is not None:
            ta10 = step(i, 10.0 * p.floor_area, tm_prev)[0]
            need = 10.0 * p.floor_area * (target - ta) / (ta10 - ta)
            hc = float(np.clip(need, min(cap, 0), max(cap, 0)))
            ta, ts, tm, tm_t = step(i, hc, tm_prev)
        t_air[i], t_s[i], t_m[i], phi_hc[i] = ta, ts, tm, hc
        tm_prev = tm_t
        ta_prev = ta
    return {"air": t_air, "surface": t_s, "mass": t_m, "phi_hc": phi_hc}


def steady_state(p: RCParams, theta_e: float, h_ve: float, phi_int: float, phi_sol: float) -> np.ndarray:
    """Independent nodal solution of the same network (used to verify ``simulate``)."""
    h_tr_is, h_tr_ms = H_IS * p.a_t, H_MS * p.a_m
    h_tr_em = 1.0 / (1.0 / p.h_tr_op - 1.0 / h_tr_ms)
    phi_ia = 0.5 * phi_int
    phi_m = p.a_m / p.a_t * (0.5 * phi_int + phi_sol)
    phi_st = (1 - p.a_m / p.a_t - p.h_tr_w / (9.1 * p.a_t)) * (0.5 * phi_int + phi_sol)
    # unknowns [air, s, m]
    g = np.array([
        [h_ve + h_tr_is, -h_tr_is, 0.0],
        [-h_tr_is, h_tr_is + p.h_tr_w + h_tr_ms, -h_tr_ms],
        [0.0, -h_tr_ms, h_tr_ms + h_tr_em],
    ])
    b = np.array([phi_ia + h_ve * theta_e, phi_st + p.h_tr_w * theta_e, phi_m + h_tr_em * theta_e])
    return np.linalg.solve(g, b)
