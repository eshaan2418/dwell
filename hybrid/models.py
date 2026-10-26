"""Trained Dwell model bundle used by the report generator.

Contents: hidden-property prior model, per-target hybrid residual GBM (fitted on all TRAIN rows),
the feature column list, and building-grouped 10-fold cross-conformal scores at two levels:
day/night level (single-day quantities) and room-mean level (seasonal averages).
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from hybrid.conformal import building_weights, weighted_quantile
from hybrid.evaluate import gbm
from hybrid.features import FAMILIES, feature_columns
from hybrid.priors import HiddenPropertyModel

BASE_COL = {"sun": "phys_mc_mean", "noise": "phys_mc_mean", "heat": "phys_mc_mean"}


@dataclass
class TargetModel:
    target: str
    columns: list[str]
    model: object
    base_col: str
    scores_row: np.ndarray
    groups_row: np.ndarray
    scores_room: np.ndarray
    groups_room: np.ndarray

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        x = rows.reindex(columns=self.columns)
        return rows[self.base_col].to_numpy(float) + self.model.predict(x)

    def halfwidth(self, level: str = "row", alpha: float = 0.1) -> float:
        s, g = (self.scores_row, self.groups_row) if level == "row" else (self.scores_room, self.groups_room)
        n_eff = len(np.unique(g))
        q = min((1 - alpha) * (1 + 1 / n_eff), 1.0)
        return float(weighted_quantile(s[None, :], building_weights(g), q)[0])


@dataclass
class DwellModels:
    hidden: HiddenPropertyModel
    targets: dict[str, TargetModel] = field(default_factory=dict)
    trained_on: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path) -> DwellModels:
        with open(path, "rb") as f:
            return pickle.load(f)


def fit_target(target: str, train: pd.DataFrame, n_folds: int = 10) -> TargetModel:
    cols = feature_columns(train, FAMILIES)
    base = BASE_COL[target]
    y = train["y"].to_numpy(float)
    oof = np.full(len(train), np.nan)
    for tr_i, ho_i in GroupKFold(n_splits=n_folds).split(train, groups=train["building"]):
        m = gbm().fit(train.iloc[tr_i][cols], y[tr_i] - train.iloc[tr_i][base].to_numpy(float))
        oof[ho_i] = train.iloc[ho_i][base].to_numpy(float) + m.predict(train.iloc[ho_i][cols])
    full = gbm().fit(train[cols], y - train[base].to_numpy(float))
    res = pd.DataFrame({"room": train["room"], "building": train["building"], "e": y - oof})
    room = res.groupby("room").agg(e=("e", "mean"), building=("building", "first"))
    return TargetModel(
        target,
        cols,
        full,
        base,
        np.abs(res["e"].to_numpy()),
        res["building"].to_numpy(),
        np.abs(room["e"].to_numpy()),
        room["building"].to_numpy(),
    )
