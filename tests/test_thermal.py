import numpy as np
import pytest

from physics.thermal.rc5r1c import RCParams, simulate, steady_state

P = RCParams(floor_area=20.0, h_tr_w=15.0, h_tr_op=10.0, mass_class="medium")


def _run(n, te=20.0, hve=10.0, pint=0.0, psol=0.0, tm0=None):
    return simulate(P, np.full(n, te), np.full(n, hve), np.full(n, pint), np.full(n, psol), tm0)


def test_no_gains_equals_outdoor():
    out = _run(48, te=17.0)
    assert np.allclose(out["air"], 17.0)


def test_steady_state_matches_nodal_solution():
    out = _run(24 * 60, te=10.0, hve=12.0, pint=200.0, psol=300.0)
    ss = steady_state(P, 10.0, 12.0, 200.0, 300.0)
    assert out["air"][-1] == pytest.approx(ss[0], abs=1e-3)
    assert out["mass"][-1] == pytest.approx(ss[2], abs=1e-3)


def test_step_response_monotone_and_time_constant_order():
    out = _run(24 * 30, te=0.0, hve=12.0, pint=500.0, tm0=0.0)
    ss = steady_state(P, 0.0, 12.0, 500.0, 0.0)[0]
    air = out["air"]
    assert np.all(np.diff(air[1:]) >= -1e-9)
    # dominant time constant ~ C_m / (H_tr_em + H_tr_3) -> order of a day for medium mass
    frac = (air - air[0]) / (ss - air[0])
    t63 = int(np.argmax(frac > 0.632))
    assert 3 < t63 < 24 * 5


def test_cooling_caps_temperature():
    p = RCParams(20.0, 15.0, 10.0, cool_setpoint=24.0, max_cool_w_m2=200.0)
    out = simulate(p, np.full(200, 30.0), np.full(200, 10.0), np.full(200, 100.0), np.full(200, 500.0))
    assert out["air"][-1] == pytest.approx(24.0, abs=1e-6)
    assert out["phi_hc"][-1] < 0
