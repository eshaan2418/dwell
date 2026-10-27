"""Render docs from templates so that every reported number comes from results/ (DoD item 4).

Placeholder syntax inside docs/templates/*.tmpl.md:

    {{ m5/sun.json#methods.hybrid.marginal.mae | .2f }}
    {{ m5/sun.json#methods.hybrid.marginal.coverage90 | pct }}       -> "89%"
    {{ m5/sun.json#methods.hybrid.marginal.mae_ci95 | ci.2f }}        -> "0.61–0.83"
    {{ m5/sun.json#provenance.data_kind }}                            -> "synthetic"

Each rendered doc gets a sidecar `<doc>.numbers.json` listing every inserted value with its source.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from core.provenance import REPO, get_path, load_result

TEMPLATES = REPO / "docs" / "templates"
TARGETS = {
    "README.tmpl.md": REPO / "README.md",
    "paper.tmpl.md": REPO / "paper" / "paper.md",
    "RESUME_BULLETS.tmpl.md": REPO / "RESUME_BULLETS.md",
    "FINAL_REVIEW.tmpl.md": REPO / "FINAL_REVIEW.md",
}
PH = re.compile(r"\{\{\s*([^#}\s]+)#([^|}\s]+)\s*(?:\|\s*([^}\s]+))?\s*\}\}")


def fmt(v: Any, spec: str | None) -> str:
    if spec is None:
        return str(v)
    if spec == "pct":
        return f"{100 * float(v):.0f}%"
    if spec.startswith("pct"):
        return f"{100 * float(v):.{int(spec[3:])}f}%"
    if spec.startswith("ci"):
        a, b = v
        s = spec[2:]
        return f"{format(float(a), s)}–{format(float(b), s)}"
    if spec == "int":
        return str(int(round(float(v))))
    return format(float(v), spec)


def render(text: str) -> tuple[str, list[dict]]:
    spans: list[dict] = []
    cache: dict[str, dict] = {}
    out, pos = [], 0
    for m in PH.finditer(text):
        path, key, spec = m.group(1), m.group(2), m.group(3)
        if path not in cache:
            cache[path] = load_result(path)
        doc = cache[path]
        if "provenance" not in doc:
            raise ValueError(f"{path} has no provenance block")
        val = get_path(doc, key)
        s = fmt(val, spec)
        out.append(text[pos : m.start()])
        start = sum(len(x) for x in out)
        out.append(s)
        spans.append(
            {
                "start": start,
                "end": start + len(s),
                "text": s,
                "source": path,
                "key": key,
                "data_kind": doc["provenance"]["data_kind"],
                "commit": doc["provenance"].get("commit"),
            }
        )
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), spans


def render_all(write: bool = True) -> dict[Path, tuple[str, list[dict]]]:
    res = {}
    for tname, target in TARGETS.items():
        tp = TEMPLATES / tname
        if not tp.exists():
            continue
        text, spans = render(tp.read_text())
        res[target] = (text, spans)
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            target.with_suffix(target.suffix + ".numbers.json").write_text(json.dumps(spans, indent=1))
    return res


def main() -> int:
    for p, (_, spans) in render_all().items():
        print(f"rendered {p.relative_to(REPO)} ({len(spans)} numbers from results/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
