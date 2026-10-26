"""Parse, clean and calibrate Dwell sensor logs (format: docs/SENSOR_LOG_FORMAT.md)."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

M_COLS = ["ts", "kit_id", "lux", "temp_c", "rh_pct", "laeq", "lamax", "la90", "batt_v", "flags"]
S_COLS = ["ts", "kit_id", "laeq_1s"]
O_COLS = ["ts", "kit_id", "l63", "l125", "l250", "l500", "l1k", "l2k", "l4k", "l8k"]
FLAG_NO_NTP, FLAG_LUX_SAT, FLAG_CLIP, FLAG_TH_ERR, FLAG_LOWBATT = 0x01, 0x02, 0x04, 0x08, 0x10


@dataclass
class KitLog:
    kit_id: str
    header: dict[str, str] = field(default_factory=dict)
    minute: pd.DataFrame = field(default_factory=pd.DataFrame)
    second: pd.DataFrame = field(default_factory=pd.DataFrame)
    octave: pd.DataFrame = field(default_factory=pd.DataFrame)
    events: pd.DataFrame = field(default_factory=pd.DataFrame)


def parse_lines(lines: list[str]) -> KitLog:
    m, s, o, e = [], [], [], []
    header: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            for tok in line[1:].split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    header[k] = v
            continue
        kind = line[0]
        body = line[2:]
        if kind == "M":
            m.append(body)
        elif kind == "S":
            s.append(body)
        elif kind == "O":
            o.append(body)
        elif kind == "E":
            e.append(body)

    def frame(rows: list[str], cols: list[str]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=cols[2:])
        df = pd.read_csv(
            io.StringIO("\n".join(rows)), names=cols, header=None, dtype={"kit_id": str}, on_bad_lines="skip"
        )
        df = df[pd.to_numeric(df["ts"], errors="coerce").notna()]
        df.index = pd.to_datetime(df["ts"].astype(np.int64), unit="s", utc=True)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.drop(columns=["ts"])

    minute = frame(m, M_COLS)
    if "flags" in minute:
        minute["flags"] = minute["flags"].apply(lambda x: int(str(x), 16) if pd.notna(x) and str(x) != "" else 0)
    events = (
        pd.DataFrame(
            [r.split(",", 3) for r in e],
            columns=["ts", "kit_id", "code", "text"][: max((len(r.split(",", 3)) for r in e), default=4)],
        )
        if e
        else pd.DataFrame()
    )
    kit = header.get("kit", str(minute["kit_id"].iloc[0]) if len(minute) else "unknown")
    return KitLog(kit, header, minute, frame(s, S_COLS), frame(o, O_COLS), events)


def parse_files(paths: list[Path]) -> KitLog:
    lines: list[str] = []
    for p in sorted(paths):
        lines.extend(Path(p).read_text(errors="replace").splitlines())
    return parse_lines(lines)


def clean_minute(df: pd.DataFrame) -> pd.DataFrame:
    """Drop impossible values / flagged readings; keep a regular 1-min UTC index (gaps = NaN)."""
    d = df.copy()
    flags = d.get("flags", pd.Series(0, index=d.index)).fillna(0).astype(int)
    d.loc[(flags & FLAG_NO_NTP) > 0, :] = np.nan  # untrustworthy timestamps
    d.loc[(flags & FLAG_TH_ERR) > 0, ["temp_c", "rh_pct"]] = np.nan
    d.loc[(flags & FLAG_CLIP) > 0, ["laeq", "lamax", "la90"]] = np.nan
    for c, lo, hi in [
        ("lux", 0, 200000),
        ("temp_c", -10, 50),
        ("rh_pct", 0, 100),
        ("laeq", 0, 130),
        ("lamax", 0, 140),
        ("la90", 0, 130),
    ]:
        if c in d:
            v = pd.to_numeric(d[c], errors="coerce")
            d[c] = v.where((v >= lo) & (v <= hi))
    # temperature spikes: > 3 C jump in 1 min is a sensor glitch
    if "temp_c" in d:
        jump = d["temp_c"].diff().abs() > 3
        d.loc[jump, "temp_c"] = np.nan
    if len(d):
        full = pd.date_range(d.index.min().floor("min"), d.index.max().ceil("min"), freq="1min")
        d.index = d.index.floor("min")
        d = d[~d.index.duplicated(keep="last")].reindex(full)
    keep = [c for c in ["lux", "temp_c", "rh_pct", "laeq", "lamax", "la90", "flags"] if c in d]
    return d[keep]


@dataclass
class Calibration:
    """Per-kit offsets from the 24-h co-location test (subtract)."""

    temp_offset: dict[str, float] = field(default_factory=dict)
    db_offset: dict[str, float] = field(default_factory=dict)
    lux_scale: dict[str, float] = field(default_factory=dict)

    def apply(self, kit_id: str, d: pd.DataFrame) -> pd.DataFrame:
        d = d.copy()
        if "temp_c" in d:
            d["temp_c"] = d["temp_c"] - self.temp_offset.get(kit_id, 0.0)
        for c in ("laeq", "lamax", "la90"):
            if c in d:
                d[c] = d[c] - self.db_offset.get(kit_id, 0.0)
        if "lux" in d:
            d["lux"] = d["lux"] * self.lux_scale.get(kit_id, 1.0)
        return d


def colocation_calibration(kits: dict[str, pd.DataFrame], ref: str | None = None) -> tuple[Calibration, dict]:
    """Estimate per-kit offsets from a co-location period (all kits side by side).

    Reference = median across kits (robust) unless ``ref`` names a reference kit. Returns the
    calibration and an agreement report (inter-kit SD before/after) for propagation into evaluation."""
    cal = Calibration()
    report: dict[str, dict] = {}
    idx = None
    for d in kits.values():
        idx = d.index if idx is None else idx.intersection(d.index)
    for col, store, kind in [
        ("temp_c", cal.temp_offset, "add"),
        ("laeq", cal.db_offset, "add"),
        ("lux", cal.lux_scale, "mul"),
    ]:
        mat = pd.DataFrame({k: d.loc[idx, col] for k, d in kits.items() if col in d})
        if mat.empty:
            continue
        if col == "laeq":
            mat = mat.where(mat > 40)  # use periods well above the mic self-noise floor
        if col == "lux":
            mat = mat.where(mat > 50)
        refser = mat[ref] if ref else mat.median(axis=1)
        before = float(mat.std(axis=1).median())
        for k in mat:
            if kind == "add":
                store[k] = float((mat[k] - refser).median())
            else:
                store[k] = float((refser / mat[k]).median())
        adj = mat.copy()
        for k in mat:
            adj[k] = mat[k] - store[k] if kind == "add" else mat[k] * store[k]
        report[col] = {
            "inter_kit_sd_before": before,
            "inter_kit_sd_after": float(adj.std(axis=1).median()),
            "n_minutes": int(mat.notna().all(axis=1).sum()),
        }
    return cal, report
