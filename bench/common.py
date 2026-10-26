"""Shared helpers for experiment scripts."""

from __future__ import annotations

import os

# gradient boosting runs inside thread pools: cap OpenMP threads per fit to avoid oversubscription
os.environ.setdefault("OMP_NUM_THREADS", "2")
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WEATHER = ROOT / "data" / "weather" / "toronto_hourly_2016_2025.csv.gz"


@lru_cache(maxsize=1)
def weather() -> pd.DataFrame:
    df = pd.read_csv(WEATHER, index_col=0, parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def pmap(fn: Callable[[Any], Any], items: list[Any], workers: int | None = None) -> list[Any]:
    workers = workers or int(os.environ.get("DWELL_WORKERS", max((os.cpu_count() or 2) - 2, 1)))
    if workers <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items, chunksize=1))
