"""Type-check ratchet: fail if mypy reports more errors than the recorded baseline (D-017)."""

from __future__ import annotations

import re
import subprocess
import sys

from core.provenance import REPO

BASELINE = REPO / "docs" / "mypy_baseline.txt"


def main() -> int:
    out = subprocess.run([sys.executable, "-m", "mypy"], cwd=REPO, capture_output=True, text=True).stdout
    m = re.search(r"Found (\d+) errors?", out)
    n = int(m.group(1)) if m else 0
    base = int(BASELINE.read_text().split()[0]) if BASELINE.exists() else n
    print(f"mypy: {n} errors (baseline {base})")
    if "--update" in sys.argv or not BASELINE.exists():
        BASELINE.write_text(f"{n}  # mypy error-count baseline; lower it as annotations are fixed\n")
        return 0
    return 0 if n <= base else 1


if __name__ == "__main__":
    sys.exit(main())
