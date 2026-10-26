"""M3 (synthetic): scan -> 2.5D geometry accuracy and scan-quality ablation.

Rooms of the frozen TEST buildings are scanned with recon/synthetic_scan.py under scan duration x
lighting x capture mode (plain video + door-height scale vs AR metric poses), then recon/floorplan.py
estimates room area, ceiling height, wall direction and windows. Real-unit accuracy (tape-measured
ground truth, HUMAN_TODO §7) is `awaiting-human`.
"""

from __future__ import annotations

import itertools

import numpy as np
from shapely.geometry import Polygon

from bench.common import pmap
from bench.synth_dataset import load, load_split
from core.provenance import hash_paths, write_result
from core.scene import Unit
from recon.floorplan import _rot, estimate_room, metric_scale
from recon.synthetic_scan import LIGHT, QUALITY, ScanConfig, scan_room

N_ROOMS = 60


def _job(args: tuple) -> list[dict]:
    room_d, wins_d, seed = args
    from core.scene import Room, Window

    room = Room(
        **{
            **room_d,
            "polygon": [tuple(p) for p in room_d["polygon"]],
            "sensor_xyz": tuple(room_d["sensor_xyz"]) if room_d.get("sensor_xyz") else None,
        }
    )
    wins = [Window(**w) for w in wins_d]
    out = []
    for dur, light, ar in itertools.product(QUALITY, LIGHT, [False, True]):
        rng = np.random.default_rng([seed, list(QUALITY).index(dur), list(LIGHT).index(light), int(ar)])
        s = scan_room(rng, room, wins, ScanConfig(dur, light, ar))
        sc = 1.0 if ar else metric_scale(s["door_heights"])[0]
        e = estimate_room(s["points"] * sc)
        true_area = Polygon(room.polygon).area
        d_err = ((e.wall_dir_deg - wins[0].azimuth) % 90 + 45) % 90 - 45
        # window matching (centre within 0.5 m along the correct wall)
        dets = []
        for w in e.windows:
            p = (
                np.array([[w["wall_pos"], w["u_centre"]]])
                if w["axis"] == 0
                else np.array([[w["u_centre"], w["wall_pos"]]])
            )
            c = _rot(p, -e.wall_dir_deg)[0]
            dets.append((c, w))
        matched, used = [], set()
        for tw in wins:
            best = None
            for k, (c, w) in enumerate(dets):
                dist = float(np.hypot(c[0] - tw.cx, c[1] - tw.cy))
                if k not in used and dist < 0.6 and (best is None or dist < best[0]):
                    best = (dist, k, w)
            if best is not None:
                used.add(best[1])
                matched.append((tw.width * tw.height, best[2]["width"] * best[2]["height"]))
        out.append(
            {
                "duration": dur,
                "lighting": light,
                "metric_ar": ar,
                "area_rel_err": float(e.area / true_area - 1),
                "ceiling_err_m": float(e.ceiling_height - room.ceiling_height),
                "dir_err_deg": float(d_err),
                "scale_rel_err": float(sc * s["scale_true"] ** -1 - 1) if not ar else 0.0,
                "n_true_windows": len(wins),
                "n_detected": len(dets),
                "n_matched": len(matched),
                "win_area_rel_err": [float(b / a - 1) for a, b in matched],
            }
        )
    return out


def main() -> None:
    test_b = set(load_split()["test_buildings"])
    recs = [r for r in load() if r["true"]["building_id"] in test_b]
    jobs = []
    for r in recs:
        u = Unit.from_dict(r["true"])
        for room in u.rooms:
            if u.windows_of(room.id) and len(jobs) < N_ROOMS:
                rd = r["true"]["rooms"][[x["id"] for x in r["true"]["rooms"]].index(room.id)]
                wd = [w for w in r["true"]["windows"] if w["room_id"] == room.id]
                jobs.append((rd, wd, len(jobs)))
    rows = [x for res in pmap(_job, jobs) for x in res]
    table = {}
    for dur, light, ar in itertools.product(QUALITY, LIGHT, [False, True]):
        sel = [x for x in rows if x["duration"] == dur and x["lighting"] == light and x["metric_ar"] == ar]
        wa = [e for x in sel for e in x["win_area_rel_err"]]
        nt, nd, nm = (sum(x[k] for x in sel) for k in ("n_true_windows", "n_detected", "n_matched"))
        table[f"{dur}__{light}__{'AR' if ar else 'door_scale'}"] = {
            "n_rooms": len(sel),
            "room_area_abs_rel_err_median": float(np.median(np.abs([x["area_rel_err"] for x in sel]))),
            "ceiling_abs_err_m_median": float(np.median(np.abs([x["ceiling_err_m"] for x in sel]))),
            "wall_dir_abs_err_deg_median": float(np.median(np.abs([x["dir_err_deg"] for x in sel]))),
            "wall_dir_abs_err_deg_p90": float(np.percentile(np.abs([x["dir_err_deg"] for x in sel]), 90)),
            "window_recall": nm / max(nt, 1),
            "window_precision": nm / max(nd, 1),
            "window_area_abs_rel_err_median": float(np.median(np.abs(wa))) if wa else None,
            "scale_abs_rel_err_median": float(np.median(np.abs([x["scale_rel_err"] for x in sel]))),
        }
    write_result(
        "m3/recon_synthetic.json",
        {
            "table": table,
            "note": "synthetic scans of synthetic rooms; thresholds "
            "of recon/floorplan.py were set by inspecting a handful of rooms (not the evaluation set).",
        },
        seed=0,
        config={"n_rooms": len(jobs), "qualities": QUALITY, "lighting_sigma_m": LIGHT},
        data_hash=hash_paths(["recon", "data/synthetic/world_v1_split.json"]),
        data_kind="synthetic",
    )
    for k, v in table.items():
        print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})


if __name__ == "__main__":
    main()
