"""Write simulated minute data as Dwell sensor log files (docs/SENSOR_LOG_FORMAT.md), one file per UTC day."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _f(x: float, nd: int) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def write_logs(d: pd.DataFrame, kit_id: str, out_dir: Path, fw: str = "sim-1.0") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for day, g in d.groupby(d.index.tz_convert("UTC").date):
        p = out_dir / f"DWELL_{kit_id}_{pd.Timestamp(day).strftime('%Y%m%d')}.log"
        ts0 = int(g.index[0].timestamp())
        lines = [f"# dwell-fw {fw} kit={kit_id} mic_offset_db=0.0 sample_rate=48000 boot={ts0}"]
        for t, r in g.iterrows():
            ts = int(t.timestamp()) + 60  # end of the averaging interval
            lines.append(
                ",".join(
                    [
                        "M",
                        str(ts),
                        kit_id,
                        _f(r.lux, 1),
                        _f(r.temp_c, 2),
                        _f(r.rh_pct, 1),
                        _f(r.laeq, 1),
                        _f(r.lamax, 1),
                        _f(r.la90, 1),
                        "",
                        "0x00",
                    ]
                )
            )
        p.write_text("\n".join(lines) + "\n")
        paths.append(p)
    return paths
