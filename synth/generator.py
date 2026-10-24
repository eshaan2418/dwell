"""Procedural Toronto-like apartments with true hidden properties and urban context.

Each synthetic *building* hosts 1-3 units (so leave-one-building-out CV is meaningful). Scenes
are built in a building frame (front facade along y'=0 with outward normal -y', building
occupying y' in [0, D]) and rotated so the front facade faces ``front_az``.

The generator returns the TRUE unit (hidden properties filled in) plus an OBSERVED copy that
mimics what Dwell would see from a scan + public geodata: noisy geometry, visual cues instead of
hidden properties, noisy/missing context (building heights from OSM levels, missing trees,
class-default traffic where counts are absent).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from core.scene import (
    FRAME_TYPES, GLAZING_TYPES, WALL_TYPES, Building, ExteriorWall, Road, Room, TransitLine, Tree, Unit,
    Window,
)
from physics.acoustics.model import AADT_BY_CLASS, SPEED_BY_CLASS
from synth import priors as P

TORONTO_GRID_DEG = -16.7  # Toronto's street grid is rotated ~17 deg anticlockwise from true north
LAT0, LON0 = 43.66, -79.40


def _rot(xy: np.ndarray, delta_deg: float) -> np.ndarray:
    """Rotate points clockwise (compass sense) by delta degrees."""
    d = np.radians(delta_deg)
    x, y = xy[..., 0], xy[..., 1]
    return np.stack([x * np.cos(d) + y * np.sin(d), -x * np.sin(d) + y * np.cos(d)], axis=-1)


def _rect(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    return np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float)


@dataclass
class BuildingSpec:
    id: str
    kind: str
    levels: int
    floor_h: float
    width: float
    depth: float
    year: int
    wall_type: str
    front_az: float
    street_class: str
    street_width: float
    seed: int


def sample_building(rng: np.random.Generator, bid: str) -> BuildingSpec:
    kind = str(rng.choice(P.KINDS, p=P.KIND_P))
    lo, hi = P.LEVELS[kind]
    levels = int(rng.integers(lo, hi + 1))
    width = {"house": (7, 12), "lowrise": (15, 35), "midrise": (25, 60), "highrise": (25, 45)}[kind]
    depth = {"house": (10, 16), "lowrise": (12, 20), "midrise": (16, 24), "highrise": (20, 30)}[kind]
    year = P.sample_year(rng, kind)
    wall = str(rng.choice(WALL_TYPES, p=P.wall_type_probs(kind, year)))
    if rng.random() < 0.75:
        front_az = (TORONTO_GRID_DEG + 90 * rng.integers(0, 4) + rng.normal(0, 2)) % 360
    else:
        front_az = rng.uniform(0, 360)
    sc_p = {"house": [0.0, 0.05, 0.1, 0.25, 0.6], "lowrise": [0.05, 0.2, 0.25, 0.25, 0.25],
            "midrise": [0.1, 0.35, 0.3, 0.15, 0.1], "highrise": [0.15, 0.35, 0.3, 0.15, 0.05]}[kind]
    sclass = str(rng.choice(["trunk", "primary", "secondary", "tertiary", "residential"], p=sc_p))
    swidth = {"trunk": 30, "primary": 24, "secondary": 20, "tertiary": 18, "residential": 15}[sclass]
    return BuildingSpec(bid, kind, levels, P.FLOOR_HEIGHT[kind], float(rng.uniform(*width)),
                        float(rng.uniform(*depth)), year, wall, float(front_az), sclass,
                        float(swidth * rng.uniform(0.85, 1.25)), int(rng.integers(1 << 31)))


def _context(rng: np.random.Generator, b: BuildingSpec) -> tuple[list[Building], list[Road], list[TransitLine],
                                                                  list[Tree]]:
    """Context in the building frame (unrotated)."""
    H = b.levels * b.floor_h
    blds = [Building(b.id, [tuple(p) for p in _rect(0, 0, b.width, b.depth)], H, year_built=b.year,
                     kind=b.kind, levels=b.levels)]

    def h_like() -> float:
        k = str(rng.choice(P.KINDS, p={"house": [0.7, 0.25, 0.05, 0.0], "lowrise": [0.35, 0.45, 0.15, 0.05],
                                         "midrise": [0.15, 0.3, 0.4, 0.15],
                                         "highrise": [0.05, 0.2, 0.35, 0.4]}[b.kind]))
        lo, hi = P.LEVELS[k]
        return float(rng.integers(lo, hi + 1) * P.FLOOR_HEIGHT[k])

    # across the street (south side in building frame, y' < 0)
    x = -60.0
    while x < b.width + 60:
        w = float(rng.uniform(8, 40))
        setback = float(rng.uniform(1, 6))
        d = float(rng.uniform(10, 25))
        y1 = -b.street_width - setback
        if rng.random() < 0.9:
            blds.append(Building(f"{b.id}_s{len(blds)}", [tuple(p) for p in _rect(x, y1 - d, x + w, y1)], h_like()))
        x += w + float(rng.uniform(0, 6))
    # side neighbours (gaps 0-8 m) and rear neighbours across a lane / yard
    for side in (-1, 1):
        gap = float(rng.choice([0.0, rng.uniform(1, 8)], p=[0.4, 0.6]))
        w = float(rng.uniform(8, 30))
        x0 = -gap - w if side < 0 else b.width + gap
        blds.append(Building(f"{b.id}_n{side}", [tuple(p) for p in _rect(x0, 0, x0 + w, b.depth * rng.uniform(0.7, 1.2))],
                             h_like()))
    rear_gap = float(rng.uniform(8, 35))
    x = -40.0
    while x < b.width + 40:
        w = float(rng.uniform(8, 30))
        d = float(rng.uniform(8, 20))
        if rng.random() < 0.8:
            blds.append(Building(f"{b.id}_r{len(blds)}",
                                 [tuple(p) for p in _rect(x, b.depth + rear_gap, x + w, b.depth + rear_gap + d)], h_like()))
        x += w + float(rng.uniform(0, 8))
    # roads: front street centreline, maybe a rear lane, maybe a parallel arterial behind
    yc = -b.street_width / 2
    aadt = AADT_BY_CLASS[b.street_class] * float(rng.lognormal(0, 0.45))
    roads = [Road(f"{b.id}_front", [(-400.0, yc), (b.width + 400.0, yc)], b.street_class, aadt=aadt,
                  speed_kmh=float(SPEED_BY_CLASS[b.street_class] * rng.uniform(0.85, 1.15)),
                  heavy_share=float(rng.uniform(0.02, 0.1)))]
    if rng.random() < 0.35:
        roads.append(Road(f"{b.id}_lane", [(-300.0, b.depth + rear_gap / 2), (b.width + 300.0, b.depth + rear_gap / 2)],
                          "service", aadt=float(300 * rng.lognormal(0, 0.5)), speed_kmh=20.0, heavy_share=0.02))
    if rng.random() < 0.4:
        dist = float(rng.uniform(60, 250))
        cls = str(rng.choice(["primary", "secondary", "trunk"], p=[0.5, 0.35, 0.15]))
        roads.append(Road(f"{b.id}_art", [(-600.0, b.depth + dist), (b.width + 600.0, b.depth + dist)], cls,
                          aadt=AADT_BY_CLASS[cls] * float(rng.lognormal(0, 0.4)),
                          speed_kmh=float(SPEED_BY_CLASS[cls]), heavy_share=float(rng.uniform(0.03, 0.12))))
    if rng.random() < 0.3:  # perpendicular cross street at one end
        xc = float(rng.choice([-rng.uniform(5, 40), b.width + rng.uniform(5, 40)]))
        cls = str(rng.choice(["residential", "tertiary", "secondary"]))
        roads.append(Road(f"{b.id}_cross", [(xc, -300.0), (xc, 300.0)], cls,
                          aadt=AADT_BY_CLASS[cls] * float(rng.lognormal(0, 0.45)), speed_kmh=float(SPEED_BY_CLASS[cls]),
                          heavy_share=0.04))
    transit = []
    if b.street_class in ("primary", "secondary") and rng.random() < 0.45:
        # Toronto streetcars: night (Blue Night) service ~2/h each direction on some routes, day ~10-20/h
        trips = [float(t) for t in ([4, 4, 4, 4, 4, 6] + [20] * 16 + [12, 8])]
        trips = [t * float(rng.uniform(0.6, 1.3)) for t in trips]
        transit.append(TransitLine(f"{b.id}_streetcar", [(-400.0, yc), (b.width + 400.0, yc)], "streetcar",
                                   trips, speed_kmh=float(rng.uniform(15, 30))))
    if rng.random() < 0.12:
        dist = float(rng.uniform(40, 300))
        side = float(rng.choice([-1, 1]))
        y_r = (b.depth + dist) if side > 0 else (-b.street_width - dist)
        trips = [float(t) for t in [1, 0, 0, 0, 1, 3] + [6] * 16 + [4, 2]]
        transit.append(TransitLine(f"{b.id}_rail", [(-800.0, y_r), (b.width + 800.0, y_r)], "rail", trips,
                                   speed_kmh=float(rng.uniform(50, 90))))
    trees = []
    if rng.random() < 0.7:
        spacing = float(rng.uniform(7, 15))
        for xt in np.arange(-30, b.width + 30, spacing):
            if rng.random() < 0.8:
                h = float(rng.uniform(6, 18))
                trees.append(Tree(float(xt + rng.normal(0, 1)), float(-rng.uniform(1.5, 3.5)), float(rng.uniform(2.5, 5.5)),
                                  h, trunk_height=float(min(2.5, h * 0.3)),
                                  porosity_leaf_on=float(rng.uniform(0.1, 0.35)),
                                  porosity_leaf_off=float(rng.uniform(0.5, 0.8))))
    if rng.random() < 0.5:
        for _ in range(int(rng.integers(1, 5))):
            h = float(rng.uniform(6, 20))
            trees.append(Tree(float(rng.uniform(0, b.width)), float(b.depth + rng.uniform(3, rear_gap)),
                              float(rng.uniform(2.5, 6)), h, trunk_height=2.5,
                              porosity_leaf_on=float(rng.uniform(0.1, 0.3)),
                              porosity_leaf_off=float(rng.uniform(0.5, 0.8))))
    return blds, roads, transit, trees


def _unit_layout(rng: np.random.Generator, b: BuildingSpec, uid: str, floor: int, facade: str, x_start: float,
                 width: float) -> tuple[list[Room], list[Window], list[ExteriorWall]]:
    """Rooms along one facade (front: y'=0, rear: y'=D) in the building frame."""
    fz = floor * b.floor_h
    ceil = float(rng.uniform(2.4, 2.9) if b.kind != "house" else rng.uniform(2.3, 3.0))
    depth = float(min(rng.uniform(3.5, 5.5), b.depth / 2 - 0.5))
    bed_w = float(min(rng.uniform(2.9, 4.2), width * 0.45))
    rooms, wins, walls = [], [], []
    spans = [("bedroom", x_start, x_start + bed_w), ("living", x_start + bed_w, x_start + width)]
    if rng.random() < 0.5:
        spans = spans[::-1]
        spans = [(spans[0][0], x_start, x_start + (spans[0][2] - spans[0][1])),
                 (spans[1][0], x_start + (spans[0][2] - spans[0][1]), x_start + width)]
    front = facade == "front"
    era_new = b.year >= 1990
    condo = b.kind in ("midrise", "highrise") and b.year >= 1995
    balcony = condo and rng.random() < 0.6
    th_mu, th_sd = P.WALL_THICKNESS[b.wall_type]
    thick = float(max(rng.normal(th_mu, th_sd), 0.1))
    for kind, x0, x1 in spans:
        rid = f"{uid}_{kind}"
        if front:
            poly = _rect(x0, 0.0, x1, depth)
            y_face = 0.0
        else:
            poly = _rect(x0, b.depth - depth, x1, b.depth)
            y_face = b.depth
        rooms.append(Room(rid, kind, [tuple(p) for p in poly], fz, ceil,
                          furnishing=str(rng.choice(["sparse", "typical", "heavy"], p=[0.2, 0.6, 0.2]))))
        L = x1 - x0
        walls.append(ExteriorWall(rid, 180.0 if front else 0.0, L, ceil, b.wall_type, None,
                                  cx=(x0 + x1) / 2, cy=y_face, base_z=fz))
        n_w = 1 if (L < 3.2 or rng.random() < 0.6) else 2
        for k in range(n_w):
            if condo:
                ww = float(min(L * rng.uniform(0.55, 0.9) / n_w, 3.0))
                wh = float(min(rng.uniform(1.8, 2.3), ceil - 0.25))
                sill = float(rng.uniform(0.05, 0.4))
            else:
                ww = float(min(rng.uniform(0.8, 1.9), L / n_w - 0.4))
                wh = float(min(rng.uniform(1.1, 1.7), ceil - 0.9))
                sill = float(rng.uniform(0.6, 0.95))
            cxk = x0 + L * (k + 0.5) / n_w
            wins.append(Window(f"{rid}_w{k}", rid, cxk, y_face, fz + sill, ww, wh, 180.0 if front else 0.0,
                               reveal_depth=float(np.clip(rng.normal(0.4, 0.1), 0.15, 0.8) * thick),
                               wall_thickness=thick,
                               overhang_depth=float(rng.uniform(1.2, 2.0)) if balcony and kind == "living" else
                               (float(rng.uniform(1.2, 2.0)) if balcony and rng.random() < 0.4 else 0.0),
                               overhang_gap=float(max(ceil - sill - wh, 0.05) + 0.25),
                               frame_fraction=float(rng.uniform(0.12, 0.2) if condo else rng.uniform(0.2, 0.3)),
                               operable=bool(rng.random() < 0.9),
                               has_blinds=bool(rng.random() < (0.75 if kind == "bedroom" else 0.45))))
        _ = era_new
    return rooms, wins, walls


def _assign_hidden(rng: np.random.Generator, b: BuildingSpec, unit: Unit) -> None:
    era = P.era_of(b.year)
    # one glazing/frame type per unit (windows replaced together), occasionally mixed
    g = str(rng.choice(GLAZING_TYPES, p=P.GLAZING_GIVEN_ERA[era]))
    f = str(rng.choice(FRAME_TYPES, p=P.FRAME_GIVEN_GLAZING[g]))
    old = b.year < 1960
    mu, sd = P.U_WALL_TRUE[(b.wall_type, old)]
    u_wall = float(mu * rng.lognormal(0, sd))
    for w in unit.windows:
        if rng.random() < 0.1:
            w.glazing = str(rng.choice(GLAZING_TYPES, p=P.GLAZING_GIVEN_ERA[era]))
        else:
            w.glazing = g
        w.frame = f if rng.random() > 0.1 else str(rng.choice(FRAME_TYPES, p=P.FRAME_GIVEN_GLAZING[w.glazing]))
    for wl in unit.walls:
        wl.wall_type = b.wall_type
        wl.u_value = u_wall


def _visual_cues(rng: np.random.Generator, b: BuildingSpec, unit: Unit) -> None:
    """What a walkthrough could plausibly observe (noisy proxies of hidden properties)."""
    panes_true = {"single": 1, "double": 2, "double_lowe": 2, "triple": 3}
    for w in unit.windows:
        pt = panes_true[w.glazing]
        r = rng.random()
        obs = pt if r < 0.7 else int(np.clip(pt + rng.choice([-1, 1]), 1, 3))
        if rng.random() < 0.15:
            obs = None  # reflections not visible in the video
        tint = bool(rng.random() < (0.6 if w.glazing in ("double_lowe", "triple") else 0.12))
        if b.year < 1960:
            mat_p = {"single": [0.75, 0.15, 0.1], "double": [0.3, 0.55, 0.15], "double_lowe": [0.15, 0.65, 0.2],
                     "triple": [0.1, 0.7, 0.2]}[w.glazing]
        else:
            mat_p = {"single": [0.3, 0.1, 0.6], "double": [0.1, 0.5, 0.4], "double_lowe": [0.05, 0.6, 0.35],
                     "triple": [0.05, 0.75, 0.2]}[w.glazing]
        frame_mat = str(rng.choice(["wood", "vinyl", "aluminum"], p=mat_p))
        draft = bool(rng.random() < {"tight": 0.03, "average": 0.12, "leaky": 0.45}[w.frame])
        w.cues = {"pane_count_obs": obs, "lowe_tint_obs": tint, "frame_material_obs": frame_mat,
                  "draft_cue_obs": draft}
    rad = bool(rng.random() < (0.7 if b.year < 1970 and b.wall_type == "masonry" else 0.12))
    unit.meta["cues"] = {"radiator_visible": rad,
                         "wall_thickness_obs": float(unit.windows[0].wall_thickness + rng.normal(0, 0.03)),
                         "exposed_brick_obs": bool(rng.random() < (0.3 if b.wall_type == "masonry" else 0.02))}


def _transform(unit: Unit, delta: float) -> None:
    """Rotate the whole scene (building frame -> ENU) clockwise by delta degrees."""
    def r2(p: tuple[float, float]) -> tuple[float, float]:
        q = _rot(np.asarray(p, float), delta)
        return float(q[0]), float(q[1])

    for room in unit.rooms:
        room.polygon = [r2(p) for p in room.polygon]
    for w in unit.windows:
        w.cx, w.cy = r2((w.cx, w.cy))
        w.azimuth = (w.azimuth + delta) % 360
    for wl in unit.walls:
        wl.cx, wl.cy = r2((wl.cx, wl.cy))
        wl.azimuth = (wl.azimuth + delta) % 360
    for bd in unit.context_buildings:
        bd.footprint = [r2(p) for p in bd.footprint]
    for rd in unit.roads:
        rd.coords = [r2(p) for p in rd.coords]
    for t in unit.transit:
        t.coords = [r2(p) for p in t.coords]
    for tr in unit.trees:
        tr.x, tr.y = r2((tr.x, tr.y))


def _sensor_positions(unit: Unit) -> None:
    for r in unit.rooms:
        wins = unit.windows_of(r.id)
        w = max(wins, key=lambda q: q.width * q.height)
        az = np.radians(w.azimuth)
        inset = w.reveal_depth + 0.08
        r.sensor_xyz = (w.cx - np.sin(az) * inset, w.cy - np.cos(az) * inset, w.sill_z + 0.03)


def generate_building_units(rng: np.random.Generator, bid: str, n_units: int) -> list[Unit]:
    b = sample_building(rng, bid)
    blds, roads, transit, trees = _context(rng, b)
    units = []
    used: set[tuple[int, str]] = set()
    for k in range(n_units):
        for _ in range(20):
            floor = int(rng.integers(1 if b.kind != "house" else 0, b.levels))
            facade = str(rng.choice(["front", "rear"]))
            if (floor, facade) not in used:
                break
        used.add((floor, facade))
        width = float(min(rng.uniform(7, 12), b.width - 0.5))
        x0 = float(rng.uniform(0, max(b.width - width, 0.01)))
        uid = f"{bid}_u{k}"
        rooms, wins, walls = _unit_layout(rng, b, uid, floor, facade, x0, width)
        u = Unit(uid, LAT0, LON0, bid, floor, rooms, wins, walls, year_built=b.year, building_kind=b.kind,
                 has_ac=bool(rng.random() < (0.55 if b.year >= 1995 else 0.25)),
                 context_buildings=copy.deepcopy(blds), roads=copy.deepcopy(roads),
                 transit=copy.deepcopy(transit), trees=copy.deepcopy(trees),
                 meta={"facade": facade, "levels": b.levels, "floor_height": b.floor_h,
                       "top_floor": floor == b.levels - 1, "street_class": b.street_class})
        _assign_hidden(rng, b, u)
        _visual_cues(rng, b, u)
        _transform(u, b.front_az - 180.0)
        _sensor_positions(u)
        units.append(u)
    return units


def observe(rng: np.random.Generator, true_unit: Unit, scan_quality: float = 1.0) -> Unit:
    """Observed version of a unit: what scan + public geodata would give (hidden properties removed).

    ``scan_quality`` scales geometric errors (1 = nominal 2-minute phone walkthrough)."""
    u = copy.deepcopy(true_unit)
    s = scan_quality
    az_err = float(rng.normal(0, 4.0 * s))  # facade azimuth error after footprint alignment
    for w in u.windows:
        w.glazing = None
        w.frame = None
        w.width *= float(rng.lognormal(0, 0.05 * s))
        w.height *= float(rng.lognormal(0, 0.05 * s))
        w.azimuth = (w.azimuth + az_err) % 360
        w.overhang_depth = max(w.overhang_depth + float(rng.normal(0, 0.15 * s)), 0.0) if w.overhang_depth > 0 else 0.0
        w.reveal_depth = max(w.reveal_depth + float(rng.normal(0, 0.03 * s)), 0.02)
    for wl in u.walls:
        wl.wall_type = None
        wl.u_value = None
        wl.azimuth = (wl.azimuth + az_err) % 360
    for r in u.rooms:
        r.ceiling_height *= float(rng.lognormal(0, 0.03 * s))
        r.furnishing = "typical"
    # geodata: OSM-like heights (levels x 3 m, +-), some buildings missing, trees partially in city data
    keep = []
    for bd in u.context_buildings:
        if bd.id != u.building_id and rng.random() < 0.05:
            continue
        lv = max(round(bd.height / 3.0 + rng.normal(0, 0.5)), 1)
        bd.height = float(lv * 3.0 * rng.lognormal(0, 0.05))
        keep.append(bd)
    u.context_buildings = keep
    u.trees = [t for t in u.trees if rng.random() < 0.6]
    for t in u.trees:  # city tree inventory gives location + DBH, crown dims modelled
        t.height *= float(rng.lognormal(0, 0.25))
        t.radius *= float(rng.lognormal(0, 0.25))
        t.porosity_leaf_on, t.porosity_leaf_off = 0.25, 0.65
    for rd in u.roads:
        counted = rd.road_class in ("trunk", "primary", "secondary") and rng.random() < 0.6
        rd.aadt = rd.aadt * float(rng.lognormal(0, 0.15)) if counted else None
        rd.speed_kmh = float(SPEED_BY_CLASS.get(rd.road_class, 40))
        rd.heavy_share = 0.05
    for t in u.transit:
        t.night_trips_per_hour = [float(x) for x in np.asarray(t.night_trips_per_hour) * rng.lognormal(0, 0.1)]
    if rng.random() < 0.2:
        u.year_built = None
    elif u.year_built is not None:
        u.year_built = int(u.year_built + rng.normal(0, 3))
    u.has_ac = true_unit.has_ac  # visible in scan (window/portable AC unit) — assumed observable
    u.meta = {k: v for k, v in u.meta.items() if k in ("levels", "floor_height", "top_floor", "street_class", "cues",
                                                       "facade")}
    return u


def generate_world(seed: int, n_buildings: int) -> list[Unit]:
    rng = np.random.default_rng(seed)
    units: list[Unit] = []
    for i in range(n_buildings):
        n = int(rng.choice([1, 2, 3], p=[0.4, 0.4, 0.2]))
        units.extend(generate_building_units(rng, f"B{i:04d}", n))
    return units
