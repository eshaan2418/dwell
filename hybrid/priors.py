"""Hidden-property inference: P(glazing, frame, wall | building metadata, visual cues).

A small Bayesian network fitted by counting (Dirichlet-smoothed), i.e. naive-Bayes cue
likelihoods on top of metadata-conditioned priors:

    P(g | era, kind) * prod_c P(cue_c | g)                         glazing  (per window)
    P(f | g)        * P(draft_cue | f)                             frame    (per window)
    P(w | kind, era) * N(wall_thickness_obs | mu_w, sd_w) * prod_c P(cue_c | w)   wall (per unit)

Missing year -> marginalise era with P(era | kind). Fitted on training units' TRUE properties
(synthetic generator, or real units whose properties were confirmed by occupant/landlord) —
"adapted on real units" = refit/update the counts with real labelled units (``update``).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.scene import FRAME_TYPES, GLAZING_TYPES, WALL_TYPES, Unit
from synth.priors import ERAS, KINDS, era_of

PANE_OBS = (None, 1, 2, 3)
MATERIALS = ("wood", "vinyl", "aluminum")


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.full_like(v, 1.0 / len(v))


@dataclass
class HiddenPosterior:
    glazing: dict[str, np.ndarray]  # window id -> P over GLAZING_TYPES
    frame: dict[str, np.ndarray]  # window id -> P over FRAME_TYPES
    wall: np.ndarray  # P over WALL_TYPES

    def map(self) -> dict[str, Any]:
        return {"glazing": {k: GLAZING_TYPES[int(np.argmax(v))] for k, v in self.glazing.items()},
                "frame": {k: FRAME_TYPES[int(np.argmax(v))] for k, v in self.frame.items()},
                "wall": WALL_TYPES[int(np.argmax(self.wall))]}

    def sample(self, rng: np.random.Generator) -> dict[str, Any]:
        """Joint sample; windows of a unit share one draw (they are usually replaced together)."""
        ids = list(self.glazing)
        pg = _norm(np.prod([self.glazing[i] for i in ids], axis=0) ** (1 / max(len(ids), 1)))
        g = GLAZING_TYPES[rng.choice(len(GLAZING_TYPES), p=pg)]
        pf = _norm(np.prod([self.frame[i] for i in ids], axis=0) ** (1 / max(len(ids), 1)))
        f = FRAME_TYPES[rng.choice(len(FRAME_TYPES), p=pf)]
        w = WALL_TYPES[rng.choice(len(WALL_TYPES), p=self.wall)]
        return {"glazing": {i: g for i in ids}, "frame": {i: f for i in ids}, "wall": w}


@dataclass
class HiddenPropertyModel:
    alpha: float = 1.0
    c_g: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(GLAZING_TYPES))))
    c_g_cue: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(GLAZING_TYPES))))
    c_f: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(FRAME_TYPES))))
    c_f_cue: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(FRAME_TYPES))))
    c_w: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(WALL_TYPES))))
    c_w_cue: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(WALL_TYPES))))
    c_era: dict = field(default_factory=lambda: defaultdict(lambda: np.zeros(len(ERAS))))
    thick: dict = field(default_factory=lambda: defaultdict(list))
    n_units: int = 0

    # ------------------------------------------------------------------ fitting
    def update(self, true_unit: Unit, obs_unit: Unit) -> None:
        """Add one labelled unit (true hidden properties + what was observed)."""
        kind = obs_unit.building_kind or "lowrise"
        year = true_unit.year_built
        era = era_of(year) if year is not None else None
        if era is not None:
            self.c_era[kind][ERAS.index(era)] += 1
        for tw, ow in zip(true_unit.windows, obs_unit.windows, strict=True):
            gi = GLAZING_TYPES.index(tw.glazing)
            fi = FRAME_TYPES.index(tw.frame)
            if era is not None:
                self.c_g[(era, kind)][gi] += 1
            cues = ow.cues
            self.c_g_cue[("pane", cues.get("pane_count_obs"))][gi] += 1
            self.c_g_cue[("tint", bool(cues.get("lowe_tint_obs")))][gi] += 1
            self.c_g_cue[("mat", cues.get("frame_material_obs"), era)][gi] += 1
            self.c_f[tw.glazing][fi] += 1
            self.c_f_cue[("draft", bool(cues.get("draft_cue_obs")))][fi] += 1
        wt = true_unit.walls[0].wall_type
        wi = WALL_TYPES.index(wt)
        if era is not None:
            self.c_w[(kind, era)][wi] += 1
        uc = obs_unit.meta.get("cues", {})
        self.c_w_cue[("rad", bool(uc.get("radiator_visible")))][wi] += 1
        self.c_w_cue[("brick", bool(uc.get("exposed_brick_obs")))][wi] += 1
        if uc.get("wall_thickness_obs") is not None:
            self.thick[wt].append(float(uc["wall_thickness_obs"]))
        self.n_units += 1

    def fit(self, pairs: list[tuple[Unit, Unit]]) -> HiddenPropertyModel:
        for t, o in pairs:
            self.update(t, o)
        return self

    # ------------------------------------------------------------------ inference
    def _p(self, counts: np.ndarray) -> np.ndarray:
        return _norm(counts + self.alpha)

    N_VALUES = {"pane": 4, "tint": 2, "mat": 3, "draft": 2, "rad": 2, "brick": 2}

    def _lik(self, table: dict, key: tuple, n: int) -> np.ndarray:
        """P(cue = key | class), Laplace-smoothed: (n_key,c + a) / (n_c + a * V).

        The conditioning context is key[2:] (e.g. era for frame material)."""
        num = table[key] + self.alpha
        den = np.zeros(n)
        for k, v in table.items():
            if k[0] == key[0] and k[2:] == key[2:]:
                den += v
        return num / (den + self.alpha * self.N_VALUES[key[0]])

    def _era_dist(self, obs: Unit) -> np.ndarray:
        kind = obs.building_kind or "lowrise"
        if obs.year_built is not None:
            e = np.zeros(len(ERAS))
            e[ERAS.index(era_of(obs.year_built))] = 1
            return e
        return self._p(self.c_era[kind])

    def posterior(self, obs: Unit, use_cues: bool = True, use_metadata: bool = True) -> HiddenPosterior:
        kind = obs.building_kind or "lowrise"
        era_p = self._era_dist(obs) if use_metadata else np.full(len(ERAS), 1 / len(ERAS))
        pg_prior = np.zeros(len(GLAZING_TYPES))
        pw_prior = np.zeros(len(WALL_TYPES))
        for ei, era in enumerate(ERAS):
            if era_p[ei] == 0:
                continue
            if use_metadata:
                pg_prior += era_p[ei] * self._p(self.c_g[(era, kind)])
                pw_prior += era_p[ei] * self._p(self.c_w[(kind, era)])
            else:
                pg_prior += era_p[ei] * self._p(sum((v for v in self.c_g.values()), np.zeros(len(GLAZING_TYPES))))
                pw_prior += era_p[ei] * self._p(sum((v for v in self.c_w.values()), np.zeros(len(WALL_TYPES))))
        eras_likely = ERAS[int(np.argmax(era_p))]
        g_post, f_post = {}, {}
        for w in obs.windows:
            pg = pg_prior.copy()
            if use_cues:
                c = w.cues
                pg *= self._lik(self.c_g_cue, ("pane", c.get("pane_count_obs")), len(GLAZING_TYPES))
                pg *= self._lik(self.c_g_cue, ("tint", bool(c.get("lowe_tint_obs"))), len(GLAZING_TYPES))
                pg *= self._lik(self.c_g_cue, ("mat", c.get("frame_material_obs"), eras_likely), len(GLAZING_TYPES))
            pg = _norm(pg)
            g_post[w.id] = pg
            pf = np.zeros(len(FRAME_TYPES))
            for gi, gname in enumerate(GLAZING_TYPES):
                pf += pg[gi] * self._p(self.c_f[gname])
            if use_cues:
                pf *= self._lik(self.c_f_cue, ("draft", bool(w.cues.get("draft_cue_obs"))), len(FRAME_TYPES))
            f_post[w.id] = _norm(pf)
        pw = pw_prior.copy()
        uc = obs.meta.get("cues", {})
        if use_cues:
            pw *= self._lik(self.c_w_cue, ("rad", bool(uc.get("radiator_visible"))), len(WALL_TYPES))
            pw *= self._lik(self.c_w_cue, ("brick", bool(uc.get("exposed_brick_obs"))), len(WALL_TYPES))
            t = uc.get("wall_thickness_obs")
            if t is not None:
                lk = []
                for wt in WALL_TYPES:
                    xs = self.thick.get(wt, [])
                    mu, sd = (float(np.mean(xs)), float(np.std(xs) + 0.02)) if len(xs) >= 3 else (0.28, 0.12)
                    lk.append(math.exp(-0.5 * ((t - mu) / sd) ** 2) / sd)
                pw *= np.array(lk)
        return HiddenPosterior(g_post, f_post, _norm(pw))


def default_assignment(obs: Unit) -> dict[str, Any]:
    """'Physics with default materials' baseline: double glazing, average frames, wall by building kind."""
    wall = {"house": "light_frame", "lowrise": "masonry", "midrise": "concrete", "highrise": "concrete"}.get(
        obs.building_kind or "lowrise", "masonry")
    return {"glazing": {w.id: "double" for w in obs.windows}, "frame": {w.id: "average" for w in obs.windows},
            "wall": wall}


def evaluate(model: HiddenPropertyModel, pairs: list[tuple[Unit, Unit]], **kw) -> dict[str, float]:
    """Accuracy and log-loss of the posterior vs true properties."""
    acc = {"glazing": [], "frame": [], "wall": []}
    ll = {"glazing": [], "frame": [], "wall": []}
    for t, o in pairs:
        post = model.posterior(o, **kw)
        for tw in t.windows:
            pg = post.glazing[tw.id]
            pf = post.frame[tw.id]
            acc["glazing"].append(float(GLAZING_TYPES[int(np.argmax(pg))] == tw.glazing))
            ll["glazing"].append(-math.log(max(pg[GLAZING_TYPES.index(tw.glazing)], 1e-9)))
            acc["frame"].append(float(FRAME_TYPES[int(np.argmax(pf))] == tw.frame))
            ll["frame"].append(-math.log(max(pf[FRAME_TYPES.index(tw.frame)], 1e-9)))
        wt = t.walls[0].wall_type
        acc["wall"].append(float(WALL_TYPES[int(np.argmax(post.wall))] == wt))
        ll["wall"].append(-math.log(max(post.wall[WALL_TYPES.index(wt)], 1e-9)))
    return {f"{k}_acc": float(np.mean(v)) for k, v in acc.items()} | {f"{k}_logloss": float(np.mean(v)) for k, v in ll.items()}


def evaluate_default(pairs: list[tuple[Unit, Unit]]) -> dict[str, float]:
    acc = {"glazing": [], "frame": [], "wall": []}
    for t, o in pairs:
        d = default_assignment(o)
        for tw in t.windows:
            acc["glazing"].append(float(d["glazing"][tw.id] == tw.glazing))
            acc["frame"].append(float(d["frame"][tw.id] == tw.frame))
        acc["wall"].append(float(d["wall"] == t.walls[0].wall_type))
    return {f"{k}_acc": float(np.mean(v)) for k, v in acc.items()}


__all__ = ["HiddenPropertyModel", "HiddenPosterior", "default_assignment", "evaluate", "evaluate_default", "KINDS",
           "PANE_OBS", "MATERIALS"]
