"""Shared scene schema: one apartment unit + its urban context.

Coordinates are local ENU metres (x = east, y = north, z = up above street level) around an
arbitrary origin near the building. Azimuths are degrees clockwise from north. A facade
azimuth is the direction the *outward* wall normal points to.

The same schema is produced by the synthetic generator (with true hidden properties), by the
reconstruction pipeline (with observed geometry + visual cues, hidden properties unknown), and
consumed by all physics modules and the app report generator.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

GLAZING_TYPES = ("single", "double", "double_lowe", "triple")
FRAME_TYPES = ("tight", "average", "leaky")
WALL_TYPES = ("light_frame", "masonry", "concrete")
FURNISHING = ("sparse", "typical", "heavy")


@dataclass
class Window:
    id: str
    room_id: str
    cx: float  # centre of the glazed opening, ENU (outer wall plane)
    cy: float
    sill_z: float  # absolute height of the sill above street level
    width: float
    height: float
    azimuth: float  # outward normal
    reveal_depth: float = 0.15  # glass set back from outer wall face (m)
    wall_thickness: float = 0.3
    overhang_depth: float = 0.0  # balcony / overhang above the window (m, horizontal)
    overhang_gap: float = 0.3  # vertical distance from window head to overhang underside
    glazing: str | None = None  # hidden property (None = unknown)
    frame: str | None = None  # hidden property: sealing quality
    frame_fraction: float = 0.25
    operable: bool = True
    has_blinds: bool = False
    cues: dict[str, Any] = field(default_factory=dict)  # visual cues from the scan


@dataclass
class Room:
    id: str
    kind: str  # bedroom | living | kitchen | other
    polygon: list[tuple[float, float]]  # ENU xy, counter-clockwise
    floor_z: float
    ceiling_height: float = 2.6
    furnishing: str = "typical"
    sensor_xyz: tuple[float, float, float] | None = None  # light/dB/temp kit position


@dataclass
class ExteriorWall:
    room_id: str
    azimuth: float
    length: float
    height: float
    wall_type: str | None = None  # hidden: light_frame | masonry | concrete
    u_value: float | None = None  # hidden: W/m2K
    cx: float = 0.0  # centre of the wall segment on the outer face (ENU)
    cy: float = 0.0
    base_z: float = 0.0  # absolute height of the wall bottom (= room floor)


@dataclass
class Building:
    id: str
    footprint: list[tuple[float, float]]
    height: float  # roof height above street (m)
    base_z: float = 0.0
    year_built: int | None = None
    kind: str | None = None  # house | lowrise | midrise | highrise
    levels: int | None = None


@dataclass
class Road:
    id: str
    coords: list[tuple[float, float]]
    road_class: str  # motorway|trunk|primary|secondary|tertiary|residential|service
    aadt: float | None = None  # annual average daily traffic (veh/day)
    speed_kmh: float = 50.0
    heavy_share: float = 0.05
    surface: str = "asphalt"


@dataclass
class TransitLine:
    id: str
    coords: list[tuple[float, float]]
    mode: str  # streetcar | subway_surface | rail | bus
    night_trips_per_hour: list[float] = field(default_factory=lambda: [0.0] * 24)  # both dirs, by hour
    speed_kmh: float = 30.0


@dataclass
class Tree:
    x: float
    y: float
    radius: float
    height: float
    trunk_height: float = 2.5
    porosity_leaf_on: float = 0.2
    porosity_leaf_off: float = 0.65


@dataclass
class Unit:
    id: str
    lat: float
    lon: float
    building_id: str
    floor: int
    rooms: list[Room]
    windows: list[Window]
    walls: list[ExteriorWall]
    year_built: int | None = None
    building_kind: str | None = None
    has_ac: bool = False
    context_buildings: list[Building] = field(default_factory=list)
    roads: list[Road] = field(default_factory=list)
    transit: list[TransitLine] = field(default_factory=list)
    trees: list[Tree] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    # ---- helpers -------------------------------------------------------------------------
    def room(self, room_id: str) -> Room:
        return next(r for r in self.rooms if r.id == room_id)

    def windows_of(self, room_id: str) -> list[Window]:
        return [w for w in self.windows if w.room_id == room_id]

    def walls_of(self, room_id: str) -> list[ExteriorWall]:
        return [w for w in self.walls if w.room_id == room_id]

    def own_building(self) -> Building | None:
        return next((b for b in self.context_buildings if b.id == self.building_id), None)

    # ---- (de)serialisation ---------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Unit:
        d = dict(d)
        d["rooms"] = [
            Room(
                **{
                    **r,
                    "polygon": [tuple(p) for p in r["polygon"]],
                    "sensor_xyz": tuple(r["sensor_xyz"]) if r.get("sensor_xyz") else None,
                }
            )
            for r in d["rooms"]
        ]
        d["windows"] = [Window(**w) for w in d["windows"]]
        d["walls"] = [ExteriorWall(**w) for w in d["walls"]]
        d["context_buildings"] = [
            Building(**{**b, "footprint": [tuple(p) for p in b["footprint"]]}) for b in d.get("context_buildings", [])
        ]
        d["roads"] = [Road(**{**r, "coords": [tuple(p) for p in r["coords"]]}) for r in d.get("roads", [])]
        d["transit"] = [TransitLine(**{**t, "coords": [tuple(p) for p in t["coords"]]}) for t in d.get("transit", [])]
        d["trees"] = [Tree(**t) for t in d.get("trees", [])]
        return Unit(**d)

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=1))

    @staticmethod
    def load(path: Path | str) -> Unit:
        return Unit.from_dict(json.loads(Path(path).read_text()))


def polygon_area(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0
