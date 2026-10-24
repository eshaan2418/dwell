"""Provenance for every result written to ``results/``.

Rule 1 of the project: every number must come from a script that records git commit,
data snapshot hash, seed, config and timestamp. ``write_result`` is the only sanctioned
way to write a result JSON.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"


def git_commit() -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=REPO, stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return ""

    commit = run("rev-parse", "HEAD") or "uncommitted"
    dirty = bool(run("status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "dirty": dirty}


def hash_paths(paths: list[Path] | list[str]) -> str:
    """Stable sha256 over file contents (sorted by path). Directories are walked."""
    h = hashlib.sha256()
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*") if q.is_file()))
        elif p.exists():
            files.append(p)
    for f in sorted(files):
        h.update(str(f.relative_to(REPO) if f.is_relative_to(REPO) else f).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def hash_obj(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=_default).encode()).hexdigest()


def _default(o: Any) -> Any:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, dt.datetime | dt.date):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def write_result(
    rel_path: str,
    payload: dict[str, Any],
    *,
    seed: int | None,
    config: dict[str, Any],
    data_hash: str,
    data_kind: str,
) -> Path:
    """Write ``results/<rel_path>`` with a provenance block.

    ``data_kind`` must be one of ``synthetic``, ``real-sensor``, ``public-dataset``, ``none`` —
    results from different kinds must never be blended into one headline number.
    """
    if data_kind not in {"synthetic", "real-sensor", "public-dataset", "none"}:
        raise ValueError(data_kind)
    out = RESULTS / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "provenance": {
            **git_commit(),
            "data_hash": data_hash,
            "data_kind": data_kind,
            "seed": seed,
            "config": config,
            "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "script": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "",
            "python": platform.python_version(),
        },
        **payload,
    }
    out.write_text(json.dumps(doc, indent=2, sort_keys=False, default=_default) + "\n")
    return out


def load_result(rel_path: str) -> dict[str, Any]:
    return json.loads((RESULTS / rel_path).read_text())


def get_path(doc: dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur
