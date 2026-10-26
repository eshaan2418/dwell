"""M4 (synthetic + real-geodata demo): orientation fusion error and horizon-profile checks.

1. Orientation: true facade azimuth vs (a) one indoor compass reading, (b) the circular mean of the
   readings logged at each window prompt, (c) snapping (b) to footprint edge normals.
   Indoor compass error sd and the footprint
   digitisation error are ASSUMPTIONS (D-016).
2. Horizon: skyline extracted from a rendered window view of the TRUE world vs (i) the true horizon
   (validates the extraction code) and (ii) the horizon from observed geodata (geodata error the
   check can reveal). Real window-view frames are `awaiting-human`.
3. Real geodata demo: OSM around a public square (Nathan Phillips Square) — horizon at street level.
"""

from __future__ import annotations

import numpy as np

from bench.synth_dataset import load, load_split
from core.provenance import hash_paths, write_result
from core.scene import Unit
from locate.orientation import TORONTO_DECLINATION_DEG, angdiff, fuse
from locate.skyline import render_skyline, skyline_elevation
from physics.sun.obstruction import horizon_profile

COMPASS_BIAS_SD = 8.0  # shared indoor magnetic bias per unit (deg), assumption
COMPASS_NOISE_SD = 8.0  # per-reading noise (deg), assumption
N_READINGS = 5  # compass readings logged at window prompts by the capture app
FOOTPRINT_ROT_SD = 1.5  # footprint digitisation rotation error (deg)


def _rot_fp(fp, deg, c):
    d = np.radians(deg)
    p = np.asarray(fp) - c
    q = np.stack([p[:, 0] * np.cos(d) + p[:, 1] * np.sin(d), -p[:, 0] * np.sin(d) + p[:, 1] * np.cos(d)], 1) + c
    return [tuple(x) for x in q]


def main() -> None:
    rng = np.random.default_rng(4)
    test_b = set(load_split()["test_buildings"])
    recs = [r for r in load() if r["true"]["building_id"] in test_b]
    errs = {"compass_single": [], "compass_averaged": [], "footprint_snap": []}
    snap_fail = 0
    sky_vs_true, geo_vs_true = [], []
    for r in recs:
        t, o = Unit.from_dict(r["true"]), Unit.from_dict(r["obs"])
        own = t.own_building()
        fp = own.footprint
        c = np.mean(np.asarray(fp), axis=0)
        fp_obs = _rot_fp(fp, rng.normal(0, FOOTPRINT_ROT_SD), c)
        for w in t.windows[:1]:
            true_az = w.azimuth
            bias = rng.normal(0, COMPASS_BIAS_SD)
            reads = true_az - TORONTO_DECLINATION_DEG + bias + rng.normal(0, COMPASS_NOISE_SD, N_READINGS)
            ang = np.radians(reads)
            mag = float(np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360)
            a = fuse(float(reads[0] % 360), None, None)
            b = fuse(mag, None, None)
            s = fuse(mag, fp_obs, None)
            errs["compass_single"].append(abs(float(angdiff(a["azimuth"], true_az))))
            errs["compass_averaged"].append(abs(float(angdiff(b["azimuth"], true_az))))
            e = abs(float(angdiff(s["azimuth"], true_az)))
            errs["footprint_snap"].append(e)
            snap_fail += int(e > 20)
            # horizon checks
            az = np.radians(w.azimuth)
            x, y, z = w.cx + 0.02 * np.sin(az), w.cy + 0.02 * np.cos(az), w.sill_z + w.height / 2
            h_true = horizon_profile(x, y, z, t.context_buildings)
            h_geo = horizon_profile(x, y, z, o.context_buildings)
            img = render_skyline(h_true.az, h_true.elevation, w.azimuth, 10.0, 60.0, (120, 160))
            saz, sel = skyline_elevation(img, w.azimuth, 10.0, 60.0)
            ok = np.isfinite(sel)
            ht = h_true.at(saz[ok])
            vis = ht > -10  # columns where a building forms the skyline inside the frame
            if vis.sum() > 5:
                sky_vs_true.append(float(np.median(np.abs(sel[ok][vis] - ht[vis]))))
                geo_vs_true.append(float(np.median(np.abs(h_geo.at(saz[ok][vis]) - ht[vis]))))
    summ = {
        k: {"median_abs_deg": float(np.median(v)), "p90_abs_deg": float(np.percentile(v, 90)), "n": len(v)}
        for k, v in errs.items()
    }
    # real-geodata demo (public location, OSM ODbL)
    demo = {}
    try:
        from locate.osm import fetch, to_scene

        lat, lon = 43.6525, -79.3832
        b, roads, transit, stats = to_scene(fetch(lat, lon, 300), lat, lon)
        h = horizon_profile(0.0, 0.0, 1.5, b)
        demo = {
            "location": "Nathan Phillips Square (public)",
            "n_buildings": len(b),
            "height_sources": stats,
            "n_roads": len(roads),
            "n_rail_tram": len(transit),
            "horizon_median_el_deg": float(np.median(np.clip(h.elevation, 0, 90))),
            "horizon_max_el_deg": float(h.elevation.max()),
        }
    except Exception as e:  # network-dependent; never fail the experiment on it
        demo = {"error": str(e)}
    write_result(
        "m4/locate.json",
        {
            "orientation": summ,
            "footprint_snap_gross_errors_gt20deg": snap_fail,
            "skyline_extraction_vs_true_median_abs_deg": float(np.median(sky_vs_true)) if sky_vs_true else None,
            "geodata_horizon_vs_true_median_abs_deg": float(np.median(geo_vs_true)) if geo_vs_true else None,
            "n_horizon_checks": len(sky_vs_true),
            "real_geodata_demo": demo,
            "assumptions": {
                "compass_bias_sd_deg": COMPASS_BIAS_SD,
                "compass_noise_sd_deg": COMPASS_NOISE_SD,
                "n_readings": N_READINGS,
                "footprint_rot_sd_deg": FOOTPRINT_ROT_SD,
            },
            "note": "SfM frames have arbitrary heading, so the reconstruction contributes only relative wall "
            "directions; absolute azimuth comes from the compass and/or the footprint.",
        },
        seed=4,
        config={"n_units": len(recs)},
        data_hash=hash_paths(["locate", "data/synthetic/world_v1_split.json"]),
        data_kind="synthetic",
    )
    print(summ, snap_fail, np.median(sky_vs_true), np.median(geo_vs_true), demo)


if __name__ == "__main__":
    main()
