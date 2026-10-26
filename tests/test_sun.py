import numpy as np
import pandas as pd
import pytest

from core.scene import Building, Room, Unit, Window
from physics.sun.daylight import aperture, rect_area, room_sun_timeseries, sun_on_windows, sun_patch_polygon
from physics.sun.obstruction import AZ_GRID, Horizon, horizon_profile, vertical_sky_view_factor
from physics.sun.solar import noaa_solar_position, solar_position, sun_vector


def test_spa_reference_example():
    # Reda & Andreas (2004) NREL SPA worked example: 2003-10-17 12:30:30 local (UTC-7)
    t = pd.DatetimeIndex([pd.Timestamp("2003-10-17 12:30:30", tz="Etc/GMT+7")])
    sp = solar_position(t, 39.742476, -105.1786, 1830.14, pressure_hpa=820, temp_c=11)
    assert sp["zenith"].iloc[0] == pytest.approx(50.11162, abs=2e-3)
    assert sp["azimuth"].iloc[0] == pytest.approx(194.34024, abs=2e-3)


def test_noaa_matches_spa_toronto_year():
    t = pd.date_range("2025-01-01", "2025-12-31", freq="37min", tz="UTC")
    a = solar_position(t, 43.65, -79.38)
    b = noaa_solar_position(t, 43.65, -79.38)
    up = a["elevation"] > 5  # above refraction-dominated band
    assert np.abs(a["azimuth"][up] - b["azimuth"][up]).max() < 0.1
    # spa elevation is refraction-corrected; NOAA here is geometric -> differ by < ~0.2 deg above 5 deg
    assert np.abs(a["elevation"][up] - b["elevation"][up]).max() < 0.25


def test_solar_noon_elevation_equinox():
    # at equinox, noon elevation ~ 90 - lat
    t = pd.date_range("2025-03-20 16:00", "2025-03-20 18:30", freq="1min", tz="UTC")
    sp = solar_position(t, 43.65, -79.38)
    assert sp["elevation"].max() == pytest.approx(90 - 43.65, abs=0.6)


def test_horizon_prism_exact():
    # 20 m tall building, wall 10 m due south of viewpoint at z=0 -> elevation atan(20/10)
    b = Building("b", [(-50, -20), (50, -20), (50, -10), (-50, -10)], 20.0)
    h = horizon_profile(0, 0, 0, [b])
    assert h.at(np.array([180.0]))[0] == pytest.approx(np.degrees(np.arctan2(20, 10)), abs=1e-6)
    assert h.at(np.array([0.0]))[0] == -90
    # oblique azimuth: distance = 10 / cos(30)
    assert h.at(np.array([150.0]))[0] == pytest.approx(
        np.degrees(np.arctan2(20, 10 / np.cos(np.radians(30)))), abs=1e-6
    )


def test_vertical_svf_unobstructed_and_obstructed():
    h = Horizon(AZ_GRID, np.full(len(AZ_GRID), -90.0))
    assert vertical_sky_view_factor(h, 180) == pytest.approx(0.5, abs=2e-3)
    h45 = Horizon(AZ_GRID, np.full(len(AZ_GRID), 45.0))
    # (1/pi) * 2 * (pi/4 - pi/8 - 1/4)
    assert vertical_sky_view_factor(h45, 180) == pytest.approx(2 / np.pi * (np.pi / 8 - 0.25), abs=2e-3)


def _win(**kw):
    d = dict(
        id="w",
        room_id="r",
        cx=0,
        cy=0,
        sill_z=1.0,
        width=1.0,
        height=1.5,
        azimuth=180.0,
        reveal_depth=0.0,
        overhang_depth=0.0,
    )
    d.update(kw)
    return Window(**d)


def test_aperture_normal_incidence_full():
    w = _win()
    s = sun_vector(np.array([180.0]), np.array([30.0]))
    assert rect_area(aperture(w, s))[0] == pytest.approx(1.5)


def test_aperture_behind_facade_zero():
    w = _win()
    s = sun_vector(np.array([0.0]), np.array([30.0]))
    assert rect_area(aperture(w, s))[0] == 0


def test_aperture_reveal_and_overhang_analytic():
    # reveal 0.2 m, sun at az 180+45 (oblique 45 deg), el 0 -> lateral shadow 0.2 m
    w = _win(reveal_depth=0.2)
    s = sun_vector(np.array([225.0]), np.array([1e-3]))
    assert rect_area(aperture(w, s))[0] == pytest.approx(0.8 * 1.5, rel=1e-3)
    # overhang depth 1 m right at head (gap 0), sun normal at el 45 -> shadow 1 m down the window
    w2 = _win(overhang_depth=1.0, overhang_gap=0.0)
    s2 = sun_vector(np.array([180.0]), np.array([45.0]))
    assert rect_area(aperture(w2, s2))[0] == pytest.approx(1.0 * 0.5, rel=1e-6)


def _unit_with(obstacle_height):
    room = Room("r", "living", [(-2, 0), (2, 0), (2, 4), (-2, 4)], floor_z=0.0)
    w = Window("w", "r", 0.0, 0.0, 0.9, 1.2, 1.5, 180.0, reveal_depth=0.1)
    bld = [Building("o", [(-200, -40), (200, -40), (200, -30), (-200, -30)], obstacle_height)]
    return Unit("u", 43.65, -79.38, "own", 3, [room], [w], [], context_buildings=bld)


def test_obstruction_reduces_sun_hours():
    t = pd.date_range("2025-12-21 05:00", "2025-12-21 23:00", freq="5min", tz="UTC")
    low = room_sun_timeseries(_unit_with(1.0), t, sun_on_windows(_unit_with(1.0), t))
    high = room_sun_timeseries(_unit_with(30.0), t, sun_on_windows(_unit_with(30.0), t))
    assert low["r"]["room_sun"].sum() > 0
    # winter-solstice noon elevation ~23 deg; a 30 m wall at 30 m subtends ~44 deg -> no sun
    assert high["r"]["room_sun"].sum() == 0


def test_sun_patch_inside_room():
    u = _unit_with(0.0)
    p = sun_patch_polygon(u, u.windows[0], 180.0, 30.0)
    assert p is not None and p.area > 0
    # patch should be on the inside (north of the window, y>0)
    assert p.centroid.y > 0
