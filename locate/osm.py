"""OpenStreetMap context (buildings, roads, rail/tram) via the Overpass API -> Dwell scene objects.

Data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright). Cached extracts
in data/geo/cache/ (git-ignored). Building heights: `height` tag, else `building:levels` x 3.0 m, else a
class default (house 7 m, apartments 12 m, other 9 m) — flagged per building (fallback rung 1).
Geocoding of private addresses (Nominatim) runs only on the owner's machine and its output stays in
data/private/.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import requests

from core.scene import Building, Road, TransitLine

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "geo" / "cache"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = {"User-Agent": "dwell-research/0.1 (local research prototype)"}
R_EARTH = 6371008.8


def to_enu(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> tuple[np.ndarray, np.ndarray]:
    """Local equirectangular projection (sub-cm error within ~1 km)."""
    x = np.radians(np.asarray(lon) - lon0) * R_EARTH * np.cos(np.radians(lat0))
    y = np.radians(np.asarray(lat) - lat0) * R_EARTH
    return x, y


HIGHWAYS = "motorway|trunk|primary|secondary|tertiary|residential|service|living_street"


def fetch(lat: float, lon: float, radius_m: float = 300.0) -> dict:
    q = f"""[out:json][timeout:60];
(
  way["building"](around:{radius_m},{lat},{lon});
  way["highway"~"{HIGHWAYS}"](around:{radius_m * 2},{lat},{lon});
  way["railway"~"rail|tram|light_rail|subway"](around:{radius_m * 2},{lat},{lon});
);
out geom tags;"""
    key = hashlib.sha256(q.encode()).hexdigest()[:16]
    path = CACHE / f"overpass_{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    import time

    last: Exception | None = None
    for attempt in range(3):
        for url in OVERPASS:
            try:
                r = requests.post(url, data={"data": q}, headers=UA, timeout=120)
                r.raise_for_status()
                data = r.json()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(r.text)
                return data
            except Exception as e:  # try the next mirror
                last = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass unavailable: {last}")


def _height(tags: dict) -> tuple[float, str]:
    h = tags.get("height")
    if h:
        try:
            return float(str(h).replace("m", "").strip()), "height_tag"
        except ValueError:
            pass
    lv = tags.get("building:levels")
    if lv:
        try:
            return float(lv) * 3.0, "levels_x3"
        except ValueError:
            pass
    b = tags.get("building", "yes")
    return {"house": 7.0, "detached": 7.0, "apartments": 12.0}.get(b, 9.0), "class_default"


def to_scene(osm: dict, lat0: float, lon0: float) -> tuple[list[Building], list[Road], list[TransitLine], dict]:
    blds, roads, transit = [], [], []
    stats = {"height_tag": 0, "levels_x3": 0, "class_default": 0}
    for el in osm.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        lat = np.array([g["lat"] for g in el["geometry"]])
        lon = np.array([g["lon"] for g in el["geometry"]])
        x, y = to_enu(lat, lon, lat0, lon0)
        coords = [(float(a), float(b)) for a, b in zip(x, y, strict=True)]
        if "building" in tags and len(coords) >= 4:
            h, src = _height(tags)
            stats[src] += 1
            levels = tags.get("building:levels")
            blds.append(
                Building(
                    f"osm{el['id']}",
                    coords[:-1] if coords[0] == coords[-1] else coords,
                    h,
                    levels=int(float(levels)) if levels and levels.replace(".", "").isdigit() else None,
                    kind=tags.get("building"),
                )
            )
        elif "highway" in tags:
            spd = tags.get("maxspeed", "")
            speed = float(spd.split()[0]) if spd.split() and spd.split()[0].isdigit() else None
            from physics.acoustics.model import SPEED_BY_CLASS

            cls = tags["highway"]
            roads.append(
                Road(f"osm{el['id']}", coords, cls, aadt=None, speed_kmh=speed or float(SPEED_BY_CLASS.get(cls, 40)))
            )
        elif "railway" in tags and tags["railway"] != "subway":
            mode = "streetcar" if tags["railway"] == "tram" else "rail"
            transit.append(TransitLine(f"osm{el['id']}", coords, mode, [0.0] * 24))
    return blds, roads, transit, stats
