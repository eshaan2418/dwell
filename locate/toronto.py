"""City of Toronto open data loaders (Open Government Licence – Toronto; attribution required).

- 3D Massing 2025 shapefile (`3DMassingShapefile_2025_WGS84`, coordinates are actually EPSG:3857
  web-mercator metres despite the name): footprints + AVG/MAX_HEIGHT above ground.
- Midblock traffic counts (`svc_most_recent_summary_data.csv`): avg_daily_vol per count location.
- TTC GTFS schedules: departures per local hour at stops near a point, by route type
  (0 = streetcar, 1 = subway, 3 = bus) — night frequencies for the transit noise sources.

Downloads are cached in data/geo/cache/ (git-ignored); see `make geo` (bench/fetch_geo.py).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from core.scene import Building, Road, TransitLine
from locate.osm import to_enu

CACHE = Path(__file__).resolve().parents[1] / "data" / "geo" / "cache"
R_MERC = 6378137.0


def merc_to_lonlat(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lon = np.degrees(np.asarray(x) / R_MERC)
    lat = np.degrees(2 * np.arctan(np.exp(np.asarray(y) / R_MERC)) - np.pi / 2)
    return lon, lat


def _massing_index(shp: Path) -> pd.DataFrame:
    idx = CACHE / "massing_2025_index.csv.gz"
    if idx.exists():
        return pd.read_csv(idx)
    import shapefile

    r = shapefile.Reader(str(shp))
    recs = r.records()
    df = pd.DataFrame(
        [(i, rec["LATITUDE"], rec["LONGITUDE"], rec["AVG_HEIGHT"], rec["MAX_HEIGHT"]) for i, rec in enumerate(recs)],
        columns=["i", "lat", "lon", "avg_h", "max_h"],
    )
    df.to_csv(idx, index=False)
    return df


def massing_buildings(lat0: float, lon0: float, radius_m: float = 300.0) -> list[Building]:
    shp = CACHE / "massing_2025" / "3DMassingShapefile_2025_WGS84"
    import shapefile

    df = _massing_index(shp)
    x, y = to_enu(df["lat"].to_numpy(), df["lon"].to_numpy(), lat0, lon0)
    near = df[np.hypot(x, y) < radius_m + 100]
    r = shapefile.Reader(str(shp))
    out = []
    for _, row in near.iterrows():
        sh = r.shape(int(row["i"]))
        pts = np.asarray(sh.points)
        if len(pts) < 3:
            continue
        parts = list(sh.parts) + [len(pts)]
        ring = pts[parts[0] : parts[1]]  # outer ring of the first part
        lon, lat = merc_to_lonlat(ring[:, 0], ring[:, 1])
        ex, ey = to_enu(lat, lon, lat0, lon0)
        fp = [(float(a), float(b)) for a, b in zip(ex, ey, strict=True)]
        if fp[0] == fp[-1]:
            fp = fp[:-1]
        h = float(row["avg_h"]) if row["avg_h"] and row["avg_h"] > 0 else float(row["max_h"] or 0)
        if h <= 0.5:
            continue
        out.append(Building(f"tm{int(row['i'])}", fp, h))
    return out


def traffic_counts(path: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(path or CACHE / "svc_most_recent_summary.csv")
    return df[["location_name", "latitude", "longitude", "avg_daily_vol", "latest_count_date_start"]].dropna(
        subset=["latitude", "longitude", "avg_daily_vol"]
    )


def attach_counts(roads: list[Road], lat0: float, lon0: float, counts: pd.DataFrame, max_dist: float = 40.0) -> int:
    """Set Road.aadt from the nearest count location within ``max_dist`` m of the road; returns #attached."""
    from shapely.geometry import LineString, Point

    x, y = to_enu(counts["latitude"].to_numpy(), counts["longitude"].to_numpy(), lat0, lon0)
    sel = np.hypot(x, y) < 3000
    pts = [(Point(a, b), v) for a, b, v in zip(x[sel], y[sel], counts["avg_daily_vol"].to_numpy()[sel], strict=True)]
    n = 0
    for rd in roads:
        ls = LineString(rd.coords)
        best = min(((ls.distance(p), v) for p, v in pts), default=(np.inf, None))
        if (
            best[1] is not None
            and best[0] < max_dist
            and rd.road_class in ("motorway", "trunk", "primary", "secondary", "tertiary")
        ):
            rd.aadt = float(best[1])
            n += 1
    return n


def gtfs_hourly_departures(
    lat0: float, lon0: float, radius_m: float = 80.0, gtfs: Path | None = None, date: str | None = None
) -> pd.DataFrame:
    """Departures per local hour (0-23, GTFS times mod 24) at stops within radius, by route_type.

    Active services for ``date`` (YYYYMMDD; default = first Wednesday of the feed) = calendar.txt weekday
    flags within the date range, plus calendar_dates additions (type 1), minus removals (type 2)."""
    z = zipfile.ZipFile(gtfs or CACHE / "ttc_gtfs.zip")
    stops = pd.read_csv(z.open("stops.txt"))
    sx, sy = to_enu(stops["stop_lat"].to_numpy(), stops["stop_lon"].to_numpy(), lat0, lon0)
    near = set(stops.loc[np.hypot(sx, sy) < radius_m, "stop_id"].astype(str))
    if not near:
        return pd.DataFrame(0.0, index=range(24), columns=["streetcar", "subway", "bus"])
    cal = pd.read_csv(z.open("calendar.txt"))
    cd = pd.read_csv(z.open("calendar_dates.txt"))
    if date is None:
        d0 = pd.Timestamp(str(cal["start_date"].min()))
        date = (d0 + pd.Timedelta(days=(2 - d0.weekday()) % 7)).strftime("%Y%m%d")
    day = pd.Timestamp(date).day_name().lower()
    inrange = (cal["start_date"] <= int(date)) & (cal["end_date"] >= int(date)) & (cal[day] == 1)
    services = set(cal.loc[inrange, "service_id"])
    services |= set(cd.loc[(cd["date"] == int(date)) & (cd["exception_type"] == 1), "service_id"])
    services -= set(cd.loc[(cd["date"] == int(date)) & (cd["exception_type"] == 2), "service_id"])
    trips = pd.read_csv(z.open("trips.txt"), usecols=["route_id", "service_id", "trip_id", "direction_id"])
    trips = trips[trips["service_id"].isin(services)]
    routes = pd.read_csv(z.open("routes.txt"), usecols=["route_id", "route_type"])
    rows = []
    for chunk in pd.read_csv(
        z.open("stop_times.txt"),
        usecols=["trip_id", "departure_time", "stop_id"],
        chunksize=1_000_000,
        dtype={"departure_time": str, "stop_id": str},
    ):
        rows.append(chunk[chunk["stop_id"].isin(near)])
    st = pd.concat(rows).merge(trips, on="trip_id").merge(routes, on="route_id")
    st = st.drop_duplicates(["trip_id"])  # one pass-by per trip near the point
    st["hour"] = st["departure_time"].str.split(":").str[0].astype(int) % 24
    kind = {0: "streetcar", 1: "subway", 3: "bus"}
    st["kind"] = st["route_type"].map(kind).fillna("bus")
    tab = st.groupby(["hour", "kind"]).size().unstack(fill_value=0).reindex(range(24), fill_value=0)
    for k in ("streetcar", "subway", "bus"):
        if k not in tab:
            tab[k] = 0
    return tab[["streetcar", "subway", "bus"]].astype(float)


def transit_lines_from_gtfs(dep: pd.DataFrame, osm_transit: list[TransitLine]) -> list[TransitLine]:
    """Assign GTFS streetcar frequencies to the nearest OSM tram lines (surface rail only)."""
    trams = [t for t in osm_transit if t.mode == "streetcar"]
    if not trams or dep["streetcar"].sum() == 0:
        return [t for t in osm_transit if t.mode != "streetcar"]
    share = dep["streetcar"].to_numpy() / len(trams)
    for t in trams:
        t.night_trips_per_hour = [float(x) for x in share]
    return trams + [t for t in osm_transit if t.mode != "streetcar"]
