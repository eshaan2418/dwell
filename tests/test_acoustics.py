import numpy as np
import pytest

from core.scene import Building, Road
from physics.acoustics.insulation import composite_r, facade_r, mass_law, tau
from physics.acoustics.levels import TRAFFIC_SPECTRUM_A, db_mean, db_sum, exceedance_level
from physics.acoustics.model import (
    Obstacles, SourceLine, a_level, discretise, incident_levels, line_lw_per_m, maekawa, path_difference,
)


def test_db_arithmetic():
    assert db_sum(np.array([60.0, 60.0])) == pytest.approx(63.0103, abs=1e-3)
    assert db_mean(np.array([60.0, 60.0])) == pytest.approx(60.0)
    assert db_mean(np.array([70.0, 0.0])) == pytest.approx(70 - 10 * np.log10(2), abs=1e-3)
    assert db_sum(TRAFFIC_SPECTRUM_A) == pytest.approx(0.0, abs=1e-9)
    lv = np.arange(100.0)
    assert exceedance_level(lv, 90) == pytest.approx(9.9, abs=0.2)


def _line_source(lw_per_m=70.0, half=3000.0):
    pts, ln = discretise([(-half, 0.0), (half, 0.0)], step=1.0)
    return SourceLine("r", "road", np.c_[pts, np.zeros(len(pts))], ln, np.full(24, lw_per_m))


def test_infinite_line_source_absolute_and_doubling():
    src = [_line_source()]
    obs = Obstacles.from_buildings([])
    l20 = a_level(incident_levels(np.array([0.0, 20.0, 0.0]), src, obs, max_dist=1e5)["r"])[0]
    l40 = a_level(incident_levels(np.array([0.0, 40.0, 0.0]), src, obs, max_dist=1e5)["r"])[0]
    # hemispherical infinite line: L = LW' - 10 lg(2 d); finite +-3 km and air absorption cost < 0.6 dB
    assert l20 == pytest.approx(70 - 10 * np.log10(40), abs=0.6)
    assert l20 - l40 == pytest.approx(3.0103, abs=0.35)


def test_line_lw_flow_doubling():
    assert line_lw_per_m(2000, 50, 96) - line_lw_per_m(1000, 50, 96) == pytest.approx(3.0103, abs=1e-3)


def test_maekawa_values():
    # N = 1 -> 10 lg(23) = 13.6 dB; path difference for N=1 at 500 Hz = 343/1000 m
    d = np.array([343.0 / 1000.0])
    att = maekawa(d)[0]
    assert att[2] == pytest.approx(10 * np.log10(23), abs=1e-6)
    assert (maekawa(np.array([100.0]))[0] == 20).all()
    assert (maekawa(np.array([-1.0]))[0] == 0).all()


def test_path_difference_barrier_geometry():
    # receiver at x=0, source at x=20, wall 1 m thick centred at x=10, 5 m tall; both at z=0
    b = Building("w", [(9.5, -100), (10.5, -100), (10.5, 100), (9.5, 100)], 5.0)
    d = path_difference(np.array([0.0, 0.0, 0.0]), np.array([[20.0, 0.0, 0.0]]), Obstacles.from_buildings([b]))
    assert d[0] == pytest.approx(np.sqrt(9.5**2 + 25) + np.sqrt(10.5**2 + 25) - 20, abs=1e-6)


def test_mass_law_and_composite():
    assert mass_law(100.0, np.array([500.0]))[0] == pytest.approx(20 * np.log10(5e4) - 47)
    assert tau(np.array([30.0]))[0] == pytest.approx(1e-3)
    # equal areas of 30 dB and 40 dB -> R = -10 lg((1e-3 + 1e-4)/2)
    r = composite_r([(1.0, np.array([30.0])), (1.0, np.array([40.0]))])
    assert r[0] == pytest.approx(-10 * np.log10(0.55e-3), abs=1e-9)


def test_open_window_dominates():
    closed = facade_r(10.0, "concrete", [(2.0, "double", "tight", 0.2)])
    ajar = facade_r(10.0, "concrete", [(2.0, "double", "tight", 0.2)], open_area=0.2)
    assert (ajar < closed - 5).all()
    assert ajar.max() < 18.0  # 0.2 m2 open in 10 m2 -> ~ 10 lg(50) = 17 dB ceiling
