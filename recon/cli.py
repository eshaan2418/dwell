"""Walkthrough -> observed unit (rung 2/3 pipeline).

  python -m recon.cli --unit U03

1. Extract frames at 2 fps from data/private/video/<unit>.mp4 (OpenCV) and store them ONLY through the
   redaction layer (semantics/redact.py) in data/private/frames/<unit>/.
2. If COLMAP is installed, run sparse SfM on the redacted frames (CPU) -> data/private/recon/<unit>/sparse
   (point cloud for recon/floorplan.py after gravity alignment + door-height scale; rung 2).
3. Geometry used for prediction: data/private/units/<unit>/floorplan.yaml (manual floor plan, rung 3, also
   used to confirm reconstructed windows) -> unit.json via recon/manual.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

from core.provenance import REPO

PRIVATE = REPO / "data" / "private"


def extract_frames(unit: str, fps: float = 2.0) -> int:
    import cv2

    from semantics.redact import redact_and_save

    video = PRIVATE / "video" / f"{unit}.mp4"
    if not video.exists():
        print("no video:", video)
        return 0
    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(round(src_fps / fps)), 1)
    out = PRIVATE / "frames" / unit
    i = n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            redact_and_save(frame, out / f"f{n:05d}.jpg", out / "manifest.json")
            n += 1
        i += 1
    return n


def run_colmap(unit: str) -> bool:
    exe = shutil.which("colmap")
    if exe is None:
        print("COLMAP not installed (brew install colmap) — skipping SfM; using manual floor plan (rung 3)")
        return False
    img = PRIVATE / "frames" / unit
    ws = PRIVATE / "recon" / unit
    ws.mkdir(parents=True, exist_ok=True)
    db = ws / "db.db"
    for args in (
        [
            "feature_extractor",
            "--database_path",
            str(db),
            "--image_path",
            str(img),
            "--ImageReader.single_camera",
            "1",
            "--SiftExtraction.use_gpu",
            "0",
        ],
        ["sequential_matcher", "--database_path", str(db), "--SiftMatching.use_gpu", "0"],
        ["mapper", "--database_path", str(db), "--image_path", str(img), "--output_path", str(ws / "sparse")],
    ):
        (ws / "sparse").mkdir(exist_ok=True)
        subprocess.run([exe, *args], check=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True)
    ap.add_argument("--skip-frames", action="store_true")
    a = ap.parse_args()
    if not a.skip_frames:
        print("frames:", extract_frames(a.unit))
        run_colmap(a.unit)
    fp = PRIVATE / "units" / a.unit / "floorplan.yaml"
    if not fp.exists():
        print("no floor plan yet:", fp, "(template: docs/templates/manual_floorplan.yaml)")
        return 0
    from recon.manual import unit_from_yaml

    u = unit_from_yaml(fp)
    (fp.parent / "unit.json").write_text(json.dumps(u.to_dict()))
    print("wrote", fp.parent / "unit.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
