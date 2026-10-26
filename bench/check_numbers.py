"""Zero unbacked numbers (DoD item 4).

For every rendered doc (README.md, paper/paper.md, RESUME_BULLETS.md, FINAL_REVIEW.md):
  1. the committed file must equal a fresh render of its template (no stale or hand-edited numbers);
  2. after removing template-inserted values, every remaining numeric token must match an entry of
     docs/number_allowlist.txt (spec targets, standards, years, milestone IDs, ...);
  3. in RESUME_BULLETS.md every bullet with a number must carry the label matching the data kind of its
     sources (`synthetic` / `real-sensor`).
"""

from __future__ import annotations

import re
import sys

from bench.render_docs import TARGETS, TEMPLATES, render
from core.provenance import REPO

NUM = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)*")


def allow_patterns() -> list[re.Pattern]:
    p = REPO / "docs" / "number_allowlist.txt"
    pats = []
    for ln in p.read_text().splitlines():
        ln = ln.split("  #")[0].rstrip()
        if ln and not ln.startswith("#"):
            pats.append(re.compile(ln))
    return pats


def check() -> list[str]:
    problems: list[str] = []
    pats = allow_patterns()
    for tname, target in TARGETS.items():
        tp = TEMPLATES / tname
        if not tp.exists():
            continue
        text, spans = render(tp.read_text())
        rel = target.relative_to(REPO)
        if not target.exists() or target.read_text() != text:
            problems.append(f"{rel}: stale or hand-edited (run `make paper`)")
        # mask inserted spans
        masked = list(text)
        for s in spans:
            for i in range(s["start"], s["end"]):
                masked[i] = " "
        mtext = "".join(masked)
        for ln_no, line in enumerate(mtext.splitlines(), 1):
            if line.strip().startswith(("```", "<!--")):
                continue
            for m in NUM.finditer(line):
                ctx = line[max(0, m.start() - 25) : m.end() + 25]
                if not any(p.search(ctx) for p in pats):
                    problems.append(f"{rel}:{ln_no}: unbacked number {m.group(0)!r} in …{ctx.strip()}…")
        if tname == "RESUME_BULLETS.tmpl.md":
            lines = text.splitlines()
            offs = 0
            for line in lines:
                end = offs + len(line)
                kinds = {s["data_kind"] for s in spans if offs <= s["start"] < end}
                for k in kinds:
                    if k in ("synthetic", "real-sensor") and f"`{k}`" not in line:
                        problems.append(f"{rel}: bullet lacks label `{k}`: {line[:80]}")
                offs = end + 1
    return problems


def main() -> int:
    probs = check()
    for p in probs:
        print("NUMBERS:", p)
    print("number check:", "OK" if not probs else f"FAIL ({len(probs)})")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
