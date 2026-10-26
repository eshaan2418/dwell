import numpy as np
import pandas as pd

from ingest.logs import clean_minute, parse_files
from ingest.targets import daily_heat, daily_sun_hours, nightly_noise
from synth.generator import generate_world
from synth.logwriter import write_logs
from synth.truth import Deployment, simulate_unit


def _weather():
    idx = pd.date_range("2025-06-25", "2025-07-10", freq="1h", tz="UTC")
    h = idx.hour.to_numpy()
    day = np.clip(np.sin((h - 10) / 24 * 2 * np.pi), 0, None)
    return pd.DataFrame(
        {
            "temp_c": 22 + 6 * day,
            "ghi": 800 * day,
            "dni": 700 * day,
            "dhi": 120 * day,
            "dni_clear": 800 * day,
            "ghi_clear": 850 * day,
            "rh_pct": 60.0,
        },
        index=idx,
    )


def test_logs_roundtrip_targets(tmp_path):
    u = generate_world(5, 1)[0]
    sim = simulate_unit(
        np.random.default_rng(0), u, _weather(), Deployment(pd.Timestamp("2025-07-01", tz="America/Toronto"), 3)
    )
    rid, d = next(iter(sim["rooms"].items()))
    write_logs(d, "K01", tmp_path)
    parsed = clean_minute(parse_files(sorted(tmp_path.glob("*.log"))).minute)
    parsed.index = parsed.index - pd.Timedelta(seconds=60)  # timestamps mark interval end
    a, b = daily_sun_hours(d, u.lat, u.lon), daily_sun_hours(parsed, u.lat, u.lon)
    common = a.index.intersection(b.index)
    assert len(common) >= 2
    assert np.allclose(a.loc[common, "sun_h"], b.loc[common, "sun_h"], atol=0.05)
    na, nb = nightly_noise(d), nightly_noise(parsed)
    c2 = na.index.intersection(nb.index)
    assert np.allclose(na.loc[c2, "laeq"], nb.loc[c2, "laeq"], atol=0.05)
    ha, hb = daily_heat(d), daily_heat(parsed)
    c3 = ha.index.intersection(hb.index)
    assert np.allclose(ha.loc[c3, "peak"], hb.loc[c3, "peak"], atol=0.02)
