"""Generative assumptions for the synthetic Toronto-like housing stock.

These are ASSUMED distributions (documented in DECISIONS.md) used only to generate synthetic
apartments. They are not measured statistics of Toronto's stock. The hidden-property inference
model is trained on samples from this generator, so any synthetic-data result inherits these
assumptions; real-unit adaptation (hybrid/priors.py) updates them from data.
"""

from __future__ import annotations

import numpy as np

KINDS = ("house", "lowrise", "midrise", "highrise")
KIND_P = np.array([0.25, 0.30, 0.25, 0.20])
LEVELS = {"house": (2, 3), "lowrise": (3, 5), "midrise": (6, 12), "highrise": (15, 40)}
FLOOR_HEIGHT = {"house": 2.9, "lowrise": 3.0, "midrise": 3.0, "highrise": 2.95}


def era_of(year: int) -> str:
    if year < 1960:
        return "pre1960"
    if year < 1990:
        return "1960_1989"
    if year < 2010:
        return "1990_2009"
    return "post2010"


ERAS = ("pre1960", "1960_1989", "1990_2009", "post2010")


def sample_year(rng: np.random.Generator, kind: str) -> int:
    if kind == "house":
        return int(rng.choice([rng.integers(1890, 1960), rng.integers(1960, 2024)], p=[0.65, 0.35]))
    if kind == "lowrise":
        return int(rng.choice([rng.integers(1900, 1960), rng.integers(1960, 2024)], p=[0.55, 0.45]))
    if kind == "midrise":
        return int(rng.choice([rng.integers(1950, 1990), rng.integers(1990, 2025)], p=[0.5, 0.5]))
    return int(rng.choice([rng.integers(1965, 1990), rng.integers(1990, 2025)], p=[0.4, 0.6]))


# P(glazing | era) over GLAZING_TYPES = single, double, double_lowe, triple
GLAZING_GIVEN_ERA = {
    "pre1960": [0.35, 0.50, 0.15, 0.00],
    "1960_1989": [0.15, 0.65, 0.20, 0.00],
    "1990_2009": [0.02, 0.50, 0.43, 0.05],
    "post2010": [0.00, 0.15, 0.73, 0.12],
}
# P(frame | glazing) over FRAME_TYPES = tight, average, leaky (shifted by era below)
FRAME_GIVEN_GLAZING = {
    "single": [0.05, 0.35, 0.60],
    "double": [0.25, 0.55, 0.20],
    "double_lowe": [0.55, 0.40, 0.05],
    "triple": [0.80, 0.20, 0.00],
}


def wall_type_probs(kind: str, year: int) -> list[float]:
    """P(wall) over WALL_TYPES = light_frame, masonry, concrete."""
    old = year < 1960
    if kind == "house":
        return [0.3, 0.7, 0.0] if old else [0.85, 0.15, 0.0]
    if kind == "lowrise":
        return [0.05, 0.9, 0.05] if old else [0.25, 0.5, 0.25]
    if kind == "midrise":
        return [0.0, 0.7, 0.3] if year < 1970 else [0.05, 0.15, 0.8]
    return [0.0, 0.05, 0.95]


U_WALL_TRUE = {  # (median, log-sd) by wall type and old/new
    ("light_frame", True): (0.7, 0.3), ("light_frame", False): (0.35, 0.25),
    ("masonry", True): (1.6, 0.25), ("masonry", False): (0.6, 0.3),
    ("concrete", True): (1.2, 0.3), ("concrete", False): (0.55, 0.3),
}
WALL_THICKNESS = {"light_frame": (0.18, 0.03), "masonry": (0.38, 0.05), "concrete": (0.27, 0.04)}
