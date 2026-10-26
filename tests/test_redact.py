import json

import numpy as np

from semantics.redact import Detections, apply_redaction, detect_all, redact_and_save


def _scene():
    import cv2

    img = np.full((360, 480, 3), 120, np.uint8)
    cv2.putText(img, "ACCOUNT 1234 5678 PRIVATE", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)
    cv2.putText(img, "Dear tenant, rent due", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (10, 10, 10), 2)
    cv2.rectangle(img, (300, 180), (440, 300), (250, 250, 250), -1)  # bright screen
    cv2.rectangle(img, (300, 180), (440, 300), (0, 0, 0), 3)
    return img


def test_text_and_screen_detected_and_blurred():
    img = _scene()
    det = detect_all(img)
    kinds = {b[4] for b in det.boxes}
    assert "text" in kinds and "screen" in kinds
    red = apply_redaction(img, det)
    # text band loses high-frequency content
    assert red[40:110, 20:400].std() < 0.5 * img[40:110, 20:400].std()


def test_redact_and_save_manifest(tmp_path):
    img = _scene()
    m = tmp_path / "manifest.json"
    redact_and_save(img, tmp_path / "f0001.jpg", m, detector=lambda x: Detections([(0, 0, 10, 10, "face")]))
    e = json.loads(m.read_text())
    assert e[0]["redacted"] and e[0]["kinds"] == ["face"]
