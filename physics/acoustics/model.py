"""Outdoor -> facade -> indoor night-noise model (fast engineering model).

Sources: road traffic (hourly flow from AADT x diurnal profile, light/heavy split, speed) and
surface transit (streetcar / rail / night bus pass-bys from GTFS frequencies). Each source line
is discretised into incoherent point sources on reflecting ground (hemispherical spreading
L = L_W - 10 lg(2 pi r^2)), with ISO 9613-1 air absorption and single-edge Maekawa screening
over the highest-impact building crossed by the source-receiver path (cap 20 dB).

Per-vehicle A-weighted sound power levels are engineering approximations (rolling +
propulsion terms) chosen to reproduce typical pass-by levels; they are an explicit uncertain
input (``emission_offset_db``) in the sensitivity analysis and residual models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

from core.scene import Building, Road, TransitLine, Unit
from physics.acoustics.insulation import absorption_area, facade_r, indoor_level
from physics.acoustics.levels import (
    A_WEIGHT, AIR_ABS_DB_PER_M, C_SOUND, OCTAVES, TRAFFIC_SPECTRUM_A, db_mean, db_sum,
)

NIGHT_HOURS = [23, 0, 1, 2, 3, 4, 5, 6]

# Fraction of daily traffic in each local hour (urban arterial weekday shape; sums to 1)
_PROFILE = np.array([1.0, 0.6, 0.45, 0.4, 0.6, 1.6, 4.2, 6.4, 6.6, 5.6, 5.2, 5.4,
                     5.6, 5.7, 6.0, 6.8, 7.5, 7.3, 6.0, 4.6, 3.8, 3.3, 2.6, 1.8])
HOURLY_TRAFFIC_PROFILE = _PROFILE / _PROFILE.sum()
NIGHT_HEAVY_FACTOR = 1.3  # heavy share relative to daily mean at night (deliveries)

# Default AADT by OSM road class (Toronto-scale assumption; used only when counts are missing)
AADT_BY_CLASS = {"motorway": 120000, "trunk": 50000, "primary": 25000, "secondary": 14000,
                 "tertiary": 7000, "residential": 1200, "service": 300, "living_street": 200}
SPEED_BY_CLASS = {"motorway": 90, "trunk": 70, "primary": 50, "secondary": 50, "tertiary": 40,
                  "residential": 30, "service": 20, "living_street": 15}


def lw_light(v_kmh: float) -> float:
    v = max(v_kmh, 20.0)
    return float(db_sum(np.array([94.0 + 30 * np.log10(v / 50), 92.0 + 10 * np.log10(v / 50)])))


def lw_heavy(v_kmh: float) -> float:
    v = max(v_kmh, 20.0)
    return float(db_sum(np.array([101.0 + 30 * np.log10(v / 50), 102.0 + 10 * np.log10(v / 50)])))


TRANSIT_LW = {"streetcar": 101.0, "rail": 110.0, "bus": 103.0, "subway_surface": 104.0}


def transit_lw(mode: str, v_kmh: float) -> float:
    return TRANSIT_LW[mode] + 25 * np.log10(max(v_kmh, 10.0) / 30.0)


def line_lw_per_m(flow_per_h: float, v_kmh: float, lw_vehicle: float) -> float:
    """A-weighted sound power per metre of an incoherent moving-source line: L_W + 10 lg(Q/(3600 v))."""
    if flow_per_h <= 0:
        return -np.inf
    return lw_vehicle + 10 * np.log10(flow_per_h / (3600.0 * v_kmh / 3.6))


def road_lw_per_m(road: Road, hour: int, aadt_scale: float = 1.0) -> float:
    aadt = (road.aadt if road.aadt is not None else AADT_BY_CLASS.get(road.road_class, 1000)) * aadt_scale
    q = aadt * HOURLY_TRAFFIC_PROFILE[hour]
    hv = min(road.heavy_share * (NIGHT_HEAVY_FACTOR if hour in NIGHT_HOURS else 1.0), 0.9)
    light = line_lw_per_m(q * (1 - hv), road.speed_kmh, lw_light(road.speed_kmh))
    heavy = line_lw_per_m(q * hv, road.speed_kmh, lw_heavy(road.speed_kmh))
    return float(db_sum(np.array([light, heavy])))


def discretise(coords: list[tuple[float, float]], step: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Points along a polyline and the length each represents."""
    line = LineString(coords)
    n = max(int(np.ceil(line.length / step)), 1)
    d = (np.arange(n) + 0.5) * line.length / n
    pts = np.array([line.interpolate(x).coords[0] for x in d])
    return pts, np.full(n, line.length / n)


def maekawa(delta: np.ndarray, f: np.ndarray = OCTAVES, cap: float = 20.0) -> np.ndarray:
    """Barrier attenuation per band (shape delta.shape + (bands,)); 0 where delta <= 0."""
    n_f = 2 * delta[..., None] * f / C_SOUND
    att = 10 * np.log10(3 + 20 * np.clip(n_f, 0, None))
    return np.where(delta[..., None] > 0, np.minimum(att, cap), 0.0)


@dataclass
class Obstacles:
    polys: list[Polygon]
    heights: np.ndarray
    tree: shapely.STRtree = field(init=False)

    def __post_init__(self) -> None:
        self.tree = shapely.STRtree(self.polys)

    @staticmethod
    def from_buildings(bs: list[Building]) -> Obstacles:
        return Obstacles([Polygon(b.footprint) for b in bs], np.array([b.height for b in bs], float))


def path_difference(rcv: np.ndarray, src: np.ndarray, obs: Obstacles) -> np.ndarray:
    """Max single-edge path difference over buildings crossed by each rcv->src path (m)."""
    n = len(src)
    delta = np.full(n, -1.0)
    if n == 0 or len(obs.polys) == 0:
        return delta
    lines = shapely.linestrings(np.stack([np.repeat(rcv[None, :2], n, 0), src[:, :2]], axis=1))
    li, bi = obs.tree.query(lines, predicate="intersects")
    if len(li) == 0:
        return delta
    inter = shapely.intersection(lines[li], np.array(obs.polys, dtype=object)[bi])
    rpt = shapely.points(np.repeat(rcv[None, :2], len(li), 0))
    d1 = shapely.distance(rpt, inter)  # receiver -> nearest crossing
    big_d = np.linalg.norm(src[li, :2] - rcv[None, :2], axis=1)
    d1 = np.clip(d1, 0.05, big_d - 0.05)
    d2 = big_d - d1
    h = obs.heights[bi]
    zr, zs = rcv[2], src[li, 2]
    z_los = zr + (zs - zr) * d1 / big_d
    dl = np.sqrt(d1**2 + (h - zr) ** 2) + np.sqrt(d2**2 + (h - zs) ** 2) - np.sqrt(big_d**2 + (zs - zr) ** 2)
    dl = np.where(z_los < h, dl, -1.0)
    np.maximum.at(delta, li, dl)
    return delta


@dataclass
class SourceLine:
    id: str
    kind: str  # road | streetcar | rail | bus
    pts: np.ndarray  # (N, 3)
    seg_len: np.ndarray
    lw_per_m_by_hour: np.ndarray  # (24,) A-weighted


def build_sources(unit: Unit, aadt_scale: float = 1.0, emission_offset_db: float = 0.0,
                  transit_scale: float = 1.0, step: float = 2.0) -> list[SourceLine]:
    out = []
    for r in unit.roads:
        pts, ln = discretise(r.coords, step)
        lw = np.array([road_lw_per_m(r, h, aadt_scale) for h in range(24)]) + emission_offset_db
        out.append(SourceLine(r.id, "road", np.c_[pts, np.full(len(pts), 0.5)], ln, lw))
    for t in unit.transit:
        pts, ln = discretise(t.coords, step)
        lw = np.array([line_lw_per_m(t.night_trips_per_hour[h] * transit_scale, t.speed_kmh,
                                     transit_lw(t.mode, t.speed_kmh)) for h in range(24)]) + emission_offset_db
        out.append(SourceLine(t.id, t.mode if t.mode != "subway_surface" else "rail",
                              np.c_[pts, np.full(len(pts), 1.0)], ln, lw))
    return out


def incident_levels(rcv: np.ndarray, sources: list[SourceLine], obs: Obstacles,
                    max_dist: float = 500.0) -> dict[str, np.ndarray]:
    """Free-field incident band levels at a receiver per source line: {id: (24, bands)} unweighted."""
    out = {}
    spec_unweighted = TRAFFIC_SPECTRUM_A - A_WEIGHT
    for s in sources:
        r = np.linalg.norm(s.pts - rcv[None, :], axis=1)
        keep = r < max_dist
        if not keep.any():
            out[s.id] = np.full((24, len(OCTAVES)), -np.inf)
            continue
        pts, ln, r = s.pts[keep], s.seg_len[keep], np.maximum(r[keep], 1.0)
        att = maekawa(path_difference(rcv, pts, obs))  # (N, B)
        geo = 10 * np.log10(ln) - 10 * np.log10(2 * np.pi * r**2)  # (N,)
        per_pt = geo[:, None] - AIR_ABS_DB_PER_M[None, :] * r[:, None] - att  # (N, B)
        base = db_sum(per_pt, axis=0)  # (B,) for 0 dB/m line
        out[s.id] = s.lw_per_m_by_hour[:, None] + spec_unweighted[None, :] + base[None, :]
    return out


def a_level(band: np.ndarray) -> np.ndarray:
    return db_sum(band + A_WEIGHT, axis=-1)


@dataclass
class NoiseParams:
    glazing: dict[str, str]  # window id -> glazing
    frame: dict[str, str]
    wall_type: str
    c_inc: float = 3.0
    emission_offset_db: float = 0.0
    aadt_scale: float = 1.0
    open_fraction: float = 0.0  # fraction of window area open (ajar scenario)


def predict_room_noise(unit: Unit, p: NoiseParams, sources: list[SourceLine] | None = None,
                       incident_cache: dict | None = None) -> dict[str, dict]:
    """Hourly indoor/outdoor A-levels per room and source attribution."""
    obs = Obstacles.from_buildings(unit.context_buildings)
    sources = sources if sources is not None else build_sources(unit, p.aadt_scale, p.emission_offset_db)
    out: dict[str, dict] = {}
    for room in unit.rooms:
        walls = unit.walls_of(room.id)
        if not walls:
            continue
        vol = Polygon(room.polygon).area * room.ceiling_height
        a_abs = absorption_area(vol, room.furnishing)
        contrib_by_src: dict[str, list[np.ndarray]] = {}
        outdoor_facade = []
        for wi, wall in enumerate(walls):
            az = np.radians(wall.azimuth)
            rcv = np.array([wall.cx + 0.5 * np.sin(az), wall.cy + 0.5 * np.cos(az),
                            wall.base_z + 1.5])
            key = (room.id, wi)
            if incident_cache is not None and key in incident_cache:
                inc = incident_cache[key]
            else:
                inc = incident_levels(rcv, sources, obs)
                if incident_cache is not None:
                    incident_cache[key] = inc
            wins = [w for w in unit.windows_of(room.id) if abs(((w.azimuth - wall.azimuth + 180) % 360) - 180) < 1]
            win_list = [(w.width * w.height, p.glazing.get(w.id, "double"), p.frame.get(w.id, "average"),
                         w.frame_fraction) for w in wins]
            open_area = p.open_fraction * sum(w.width * w.height for w in wins)
            s_area = wall.length * wall.height
            r_band = facade_r(s_area, p.wall_type, win_list, open_area)
            for sid, band in inc.items():
                lin = indoor_level(band, r_band, s_area, a_abs, p.c_inc)
                contrib_by_src.setdefault(sid, []).append(lin)
            outdoor_facade.append(a_level(db_sum(np.stack(list(inc.values())), axis=0)) if inc else None)
        kinds = {s.id: s.kind for s in sources}
        per_src_a = {sid: a_level(db_sum(np.stack(v), axis=0)) for sid, v in contrib_by_src.items()}
        indoor_hourly = db_sum(np.stack(list(per_src_a.values())), axis=0) if per_src_a else np.full(24, -np.inf)
        by_kind: dict[str, np.ndarray] = {}
        for sid, lv in per_src_a.items():
            k = kinds[sid]
            by_kind[k] = db_sum(np.stack([by_kind[k], lv]), axis=0) if k in by_kind else lv
        out[room.id] = {
            "indoor_hourly": indoor_hourly,
            "outdoor_facade_hourly": db_sum(np.stack([o for o in outdoor_facade if o is not None]), axis=0)
            if outdoor_facade else np.full(24, -np.inf),
            "by_kind_hourly": by_kind,
            "night_laeq": float(db_mean(indoor_hourly[NIGHT_HOURS])),
        }
    return out


def night_laeq(hourly: np.ndarray) -> float:
    return float(db_mean(np.asarray(hourly)[NIGHT_HOURS]))
