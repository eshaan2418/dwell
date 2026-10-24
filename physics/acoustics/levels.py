"""Sound-level arithmetic and constants."""

from __future__ import annotations

import numpy as np

OCTAVES = np.array([125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0])
# IEC 61672-1 A-weighting at octave centres (dB)
A_WEIGHT = np.array([-16.1, -8.6, -3.2, 0.0, 1.2, 1.0])
# ISO 717-1 spectrum No. 2 (urban road traffic), A-weighted, octave bands, normalised to 0 dB(A) total
TRAFFIC_SPECTRUM_A = np.array([-14.0, -10.0, -7.0, -4.0, -6.0, -11.0])
# ISO 9613-1 atmospheric absorption, 10 C / 70 % RH, dB per metre
AIR_ABS_DB_PER_M = np.array([0.4, 1.0, 1.9, 3.7, 9.7, 32.8]) / 1000.0
C_SOUND = 343.0


def db_sum(levels: np.ndarray, axis: int | None = None) -> np.ndarray:
    """Energetic sum of levels in dB."""
    lv = np.asarray(levels, float)
    with np.errstate(divide="ignore"):
        return 10 * np.log10(np.sum(10 ** (lv / 10), axis=axis))


def db_mean(levels: np.ndarray, axis: int | None = None) -> np.ndarray:
    """Energetic mean (L_eq over equal-length intervals)."""
    lv = np.asarray(levels, float)
    with np.errstate(divide="ignore"):
        return 10 * np.log10(np.nanmean(10 ** (lv / 10), axis=axis))


def exceedance_level(levels: np.ndarray, pct: float) -> float:
    """L_N: level exceeded N % of the time (e.g. L90 -> pct=90)."""
    return float(np.nanpercentile(np.asarray(levels, float), 100 - pct))


def normalised_spectrum(spec_a: np.ndarray) -> np.ndarray:
    """Shift an A-weighted band spectrum so its energetic total is 0 dB(A)."""
    return spec_a - db_sum(spec_a)


TRAFFIC_SPECTRUM_A = normalised_spectrum(TRAFFIC_SPECTRUM_A)
