"""Manual floor plan (docs/templates/manual_floorplan.yaml) + public geodata -> observed Unit.

Rooms are laid out side by side along one facade (single-aspect unit), which covers the
capture-fallback rung; multi-aspect units need one YAML per facade (future work).
Geodata: Toronto 3D Massing (heights) where available, else OSM; OSM roads with Toronto midblock counts;
OSM tram/rail with TTC GTFS streetcar frequencies.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from core.scene import Building, ExteriorWall, Room, Unit, Window
from locate.orientation import TORONTO_DECLINATION_DEG, fuse


def _rot(x: float, y: float, deg: float) -> tuple[float, float]:
    d = np.radians(deg)
    return float(x * np.cos(d) + y * np.sin(d)), float(-x * np.sin(d) + y * np.cos(d))


def unit_from_yaml(path: Path, with_geodata: bool = True, radius_m: float = 300.0) -> Unit:
    c = yaml.safe_load(Path(path).read_text())
    lat, lon = float(c["lat"]), float(c["lon"])
    fz = float(c["floor"]) * float(c.get("floor_height_m", 3.0))
    blds: list[Building] = []
    roads, transit = [], []
    if with_geodata:
        from locate.osm import fetch, to_scene

        ob, roads, transit, _ = to_scene(fetch(lat, lon, radius_m), lat, lon)
        try:
            from locate.toronto import (
                attach_counts,
                gtfs_hourly_departures,
                massing_buildings,
                traffic_counts,
            )

            blds = massing_buildings(lat, lon, radius_m) or ob
            attach_counts(roads, lat, lon, traffic_counts())
            from locate.toronto import transit_lines_from_gtfs

            transit = transit_lines_from_gtfs(gtfs_hourly_departures(lat, lon, 120.0), transit)
        except Exception:  # Toronto layers not downloaded: OSM only (fallback rung 1)
            blds = ob
    # own building = footprint containing (or nearest to) the unit point
    from shapely.geometry import Point, Polygon

    own = min(blds, key=lambda b: Polygon(b.footprint).distance(Point(0, 0))) if blds else None
    az = fuse(float(c["main_facade_compass_deg"]), own.footprint if own else None)["azimuth"]
    # building frame: facade along x', outward normal -y' (azimuth 180) -> rotate by az - 180
    delta = az - 180.0
    rooms, wins, walls = [], [], []
    for r in c["rooms"]:
        rid = f"{c['unit_pid']}_{r['id']}"
        x0, w, d = float(r.get("offset_m", 0.0)), float(r["width_m"]), float(r["depth_m"])
        poly = [_rot(x, y, delta) for x, y in [(x0, 0), (x0 + w, 0), (x0 + w, d), (x0, d)]]
        rooms.append(Room(rid, r["kind"], poly, fz, float(r["ceiling_m"])))
        cx, cy = _rot(x0 + w / 2, 0.0, delta)
        walls.append(ExteriorWall(rid, az, w, float(r["ceiling_m"]), cx=cx, cy=cy, base_z=fz))
        for k, wd in enumerate(r.get("windows", [])):
            wx, wy = _rot(x0 + float(wd["offset_m"]), 0.0, delta)
            wins.append(
                Window(
                    f"{rid}_w{k}",
                    rid,
                    wx,
                    wy,
                    fz + float(wd["sill_m"]),
                    float(wd["width_m"]),
                    float(wd["height_m"]),
                    az,
                    reveal_depth=float(wd.get("reveal_m", 0.15)),
                    overhang_depth=float(wd.get("overhang_m", 0.0)),
                    has_blinds=bool(wd.get("has_blinds")),
                    cues={
                        "pane_count_obs": wd.get("pane_count_seen"),
                        "lowe_tint_obs": bool(wd.get("lowe_tint_seen")),
                        "frame_material_obs": wd.get("frame_material"),
                        "draft_cue_obs": bool(wd.get("drafty")),
                    },
                )
            )
    # snap: move the unit so its facade line lies on the own-building footprint edge whose outward normal
    # matches the fused azimuth (geocoded points are rarely exactly on the facade)
    if own is not None:
        from locate.orientation import angdiff, edge_normals

        fp = np.asarray(own.footprint, float)
        normals = edge_normals(own.footprint)
        k = int(np.argmin(np.abs(angdiff(normals, az))))
        a_, b_ = fp[k], fp[(k + 1) % len(fp)]
        e = b_ - a_
        t = float(np.clip(np.dot(-a_, e) / np.dot(e, e), 0.0, 1.0))
        p_e = a_ + t * e
        sx, sy = float(p_e[0]), float(p_e[1])
        for rm in rooms:
            rm.polygon = [(x + sx, y + sy) for x, y in rm.polygon]
        for wn in wins:
            wn.cx, wn.cy = wn.cx + sx, wn.cy + sy
        for wl in walls:
            wl.cx, wl.cy = wl.cx + sx, wl.cy + sy
    meta = {
        "cues": {
            "radiator_visible": bool(c.get("cues", {}).get("radiator_visible")),
            "exposed_brick_obs": bool(c.get("cues", {}).get("exposed_brick")),
            "wall_thickness_obs": c.get("cues", {}).get("wall_thickness_m"),
        },
        "declination_deg": TORONTO_DECLINATION_DEG,
    }
    return Unit(
        c["unit_pid"],
        lat,
        lon,
        own.id if own else "unknown",
        int(c["floor"]),
        rooms,
        wins,
        walls,
        year_built=c.get("year_built"),
        building_kind=c.get("building_kind"),
        has_ac=bool(c.get("has_ac")),
        context_buildings=blds,
        roads=roads,
        transit=transit,
        meta=meta,
    )
