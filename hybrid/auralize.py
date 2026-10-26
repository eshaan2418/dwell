"""Illustrative "listen to this room at 2 am" synthesis (NOT a recording, NOT calibrated playback).

Noise is shaped per octave band to the predicted indoor band spectrum, with a slowly varying
envelope and discrete pass-by events whose rate follows the predicted night traffic / transit
frequency. Absolute level mapping is fixed (dBFS = L_A - 90) so files are comparable across
rooms and units, but playback loudness depends on the listener's device.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

from physics.acoustics.levels import A_WEIGHT, OCTAVES, db_sum

SR = 22050
DBFS_OFFSET = 90.0


def synthesize(
    band_levels_db: np.ndarray, pass_rate_per_min: float, seconds: float = 12.0, seed: int = 0, transit_events: int = 0
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    t = np.arange(n) / SR
    # pass-by envelope: sum of Gaussian bumps (each ~3-6 s) on top of a residual hum
    env = np.full(n, 0.35)
    n_events = rng.poisson(pass_rate_per_min * seconds / 60.0)
    for _ in range(n_events):
        c, w = rng.uniform(0, seconds), rng.uniform(1.5, 3.0)
        env += rng.uniform(0.6, 1.6) * np.exp(-0.5 * ((t - c) / w) ** 2)
    for _ in range(transit_events):
        c, w = rng.uniform(2, seconds - 2), rng.uniform(2.5, 4.0)
        env += 2.5 * np.exp(-0.5 * ((t - c) / w) ** 2)
    env /= np.sqrt(np.mean(env**2))
    out = np.zeros(n)
    for f, lv in zip(OCTAVES, band_levels_db, strict=True):
        if not np.isfinite(lv):
            continue
        sos = butter(2, [f / np.sqrt(2), min(f * np.sqrt(2), SR / 2 * 0.95)], btype="band", fs=SR, output="sos")
        x = sosfilt(sos, rng.normal(size=n))
        x /= np.sqrt(np.mean(x**2)) + 1e-12
        out += x * 10 ** ((lv - DBFS_OFFSET) / 20)
    out *= env
    fade = np.minimum(1, np.minimum(t, seconds - t) / 0.5)
    return out * fade


def a_level_of_bands(bands: np.ndarray) -> float:
    return float(db_sum(bands + A_WEIGHT))


def write_wav(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())
