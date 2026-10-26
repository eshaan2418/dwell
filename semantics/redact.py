"""Privacy redaction for walkthrough frames (faces, documents/text, screens, framed photos).

Fail-closed policy: frames are only ever written to disk through ``redact_and_save``, which blurs every
detected region (generous padding) and records a manifest entry. Detectors are deliberately
over-inclusive; a false positive costs a blurred patch, a false negative may leak private content, so
figures from real homes additionally require per-unit consent code F and a manual check (HUMAN_TODO).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Detections:
    boxes: list[tuple[int, int, int, int, str]] = field(default_factory=list)  # x, y, w, h, kind


YUNET = Path(__file__).resolve().parents[1] / "data" / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


class FaceDetectorUnavailable(RuntimeError):
    pass


def detect_faces(img: np.ndarray, score: float = 0.6) -> list[tuple[int, int, int, int, str]]:
    """YuNet (OpenCV zoo, ONNX). Fail-closed: raises if the model is missing (see `make models`)."""
    import cv2

    if not YUNET.exists():
        raise FaceDetectorUnavailable(f"face model missing: {YUNET} (download from {YUNET_URL})")
    bgr = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), score, 0.3, 5000)
    _, faces = det.detect(bgr)
    if faces is None:
        return []
    return [(int(f[0]), int(f[1]), int(f[2]), int(f[3]), "face") for f in faces]


def detect_text(gray: np.ndarray) -> list[tuple[int, int, int, int, str]]:
    """Text-like regions: dense small high-contrast strokes (morphological gradient + closing)."""
    import cv2

    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        fill = area / max(w * h, 1)
        if w > 25 and 6 < h < 0.2 * gray.shape[0] and w > 1.5 * h and fill > 0.35:
            out.append((int(x), int(y), int(w), int(h), "text"))
    return out


def detect_screens_and_frames(img: np.ndarray) -> list[tuple[int, int, int, int, str]]:
    """Quadrilaterals that are much brighter (screens) or much more textured (photos/posters) than surroundings."""
    import cv2

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    edges = cv2.Canny(gray, 50, 150)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    H, W = gray.shape
    out = []
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    g_mean, t_mean = float(gray.mean()), float(lap.mean())
    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.03 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        x, y, w, h = cv2.boundingRect(approx)
        if w * h < 0.004 * H * W or w * h > 0.5 * H * W:
            continue
        roi_g, roi_t = gray[y : y + h, x : x + w], lap[y : y + h, x : x + w]
        if roi_g.mean() > g_mean + 40:
            out.append((x, y, w, h, "screen"))
        elif roi_t.mean() > 2.0 * t_mean:
            out.append((x, y, w, h, "photo_or_document"))
    return out


def detect_all(img: np.ndarray) -> Detections:
    import cv2

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return Detections(detect_faces(img) + detect_text(gray) + detect_screens_and_frames(img))


def apply_redaction(img: np.ndarray, det: Detections, pad: float = 0.25) -> np.ndarray:
    import cv2

    out = img.copy()
    H, W = img.shape[:2]
    for x, y, w, h, _ in det.boxes:
        px, py = int(w * pad), int(h * pad)
        x0, y0, x1, y1 = max(x - px, 0), max(y - py, 0), min(x + w + px, W), min(y + h + py, H)
        roi = out[y0:y1, x0:x1]
        if roi.size == 0:
            continue
        k = max(int(min(roi.shape[:2]) // 3) | 1, 15)
        small = cv2.resize(roi, (max(roi.shape[1] // 12, 1), max(roi.shape[0] // 12, 1)), interpolation=cv2.INTER_AREA)
        out[y0:y1, x0:x1] = cv2.GaussianBlur(
            cv2.resize(small, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST), (k, k), 0
        )
    return out


def redact_and_save(img: np.ndarray, path: Path, manifest: Path, detector=detect_all) -> Detections:
    """The ONLY sanctioned way to store a frame."""
    import cv2

    det = detector(img)
    red = apply_redaction(img, det)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), red)
    entries = json.loads(manifest.read_text()) if manifest.exists() else []
    entries.append(
        {"file": path.name, "n_regions": len(det.boxes), "kinds": sorted({b[4] for b in det.boxes}), "redacted": True}
    )
    manifest.write_text(json.dumps(entries, indent=1))
    return det
