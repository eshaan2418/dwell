"""Fetch and merge Toronto hourly weather.

- ECCC hourly observations, station TORONTO CITY (stationID 31688, climate ID 6158355): air temp,
  RH, wind, station pressure, weather text. Times are LST (UTC-5, no DST). Licence: Open Government
  Licence - Canada (Environment and Climate Change Canada historical climate data).
- NASA POWER hourly (CERES SYN1deg irradiance, MERRA-2 met) at the same point: GHI, DNI, DHI,
  clear-sky GHI/DNI (UTC). NASA POWER data are free to use with attribution.

Output: data/weather/toronto_hourly_<y0>_<y1>.csv.gz (UTC index), committed so that
reproduction does not depend on network access. Raw downloads are cached in data/weather/cache/.
"""

from __future__ import annotations

import argparse
import io
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "weather" / "cache"
LAT, LON = 43.6532, -79.3832
ECCC = ("https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=31688"
        "&Year={y}&Month={m}&Day=1&timeframe=1&submit=Download+Data")
POWER = ("https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=ALLSKY_SFC_SW_DWN,"
         "ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,CLRSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DNI,T2M,RH2M,WS10M"
         "&community=RE&longitude={lon}&latitude={lat}&start={y}0101&end={y}1231&format=CSV&time-standard=UTC")


def _get(url: str, path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8-sig")
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(r.text, encoding="utf-8")
            time.sleep(0.3)
            return r.text.lstrip("﻿")
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}")


def eccc_year(y: int) -> pd.DataFrame:
    frames = []
    for m in range(1, 13):
        txt = _get(ECCC.format(y=y, m=m), CACHE / f"eccc_31688_{y}_{m:02d}.csv")
        df = pd.read_csv(io.StringIO(txt))
        frames.append(df)
    df = pd.concat(frames)
    t = pd.to_datetime(df["Date/Time (LST)"]).dt.tz_localize("Etc/GMT+5").dt.tz_convert("UTC")
    out = pd.DataFrame({
        "temp_c": pd.to_numeric(df["Temp (°C)"], errors="coerce").to_numpy(),
        "rh_pct": pd.to_numeric(df["Rel Hum (%)"], errors="coerce").to_numpy(),
        "wind_kmh": pd.to_numeric(df["Wind Spd (km/h)"], errors="coerce").to_numpy(),
        "weather": df["Weather"].astype(str).to_numpy(),
    }, index=pd.DatetimeIndex(t, name="time_utc"))
    return out[~out.index.duplicated()]


def power_year(y: int) -> pd.DataFrame:
    txt = _get(POWER.format(y=y, lat=LAT, lon=LON), CACHE / f"power_{y}.csv")
    body = txt.split("-END HEADER-")[1].strip()
    df = pd.read_csv(io.StringIO(body))
    t = pd.to_datetime(dict(year=df.YEAR, month=df.MO, day=df.DY, hour=df.HR)).dt.tz_localize("UTC")
    df = df.set_index(pd.DatetimeIndex(t, name="time_utc")).replace(-999.0, float("nan"))
    return pd.DataFrame({
        "ghi": df.ALLSKY_SFC_SW_DWN, "dni": df.ALLSKY_SFC_SW_DNI, "dhi": df.ALLSKY_SFC_SW_DIFF,
        "ghi_clear": df.CLRSKY_SFC_SW_DWN, "dni_clear": df.CLRSKY_SFC_SW_DNI,
        "t2m_power": df.T2M, "rh2m_power": df.RH2M,
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--y0", type=int, default=2016)
    ap.add_argument("--y1", type=int, default=2025)
    a = ap.parse_args()
    frames = []
    for y in range(a.y0, a.y1 + 1):
        e, p = eccc_year(y), power_year(y)
        frames.append(p.join(e, how="left"))
        print(y, len(p), int(e["temp_c"].notna().sum()))
    df = pd.concat(frames)
    # fill ECCC gaps with MERRA-2 2 m temperature (flagged)
    df["temp_filled"] = df["temp_c"].isna()
    df["temp_c"] = df["temp_c"].fillna(df["t2m_power"])
    df["rh_pct"] = df["rh_pct"].fillna(df["rh2m_power"])
    out = ROOT / "data" / "weather" / f"toronto_hourly_{a.y0}_{a.y1}.csv.gz"
    df.round(3).to_csv(out)
    print("wrote", out, len(df))


if __name__ == "__main__":
    main()
