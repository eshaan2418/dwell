"""Balanced, seeded assignment schedule for the M11 decision study.

Design (see study/README.md, "Randomisation"):

* Participants are processed in *twin blocks* of two. Both twins see the same K pairs (the K pairs
  with the lowest exposure so far, random tie-break) and receive complementary condition splits: the
  pairs twin 1 sees with the Dwell report, twin 2 sees as video-only and vice versa. Hence, for an even
  number of participants, every pair is shown exactly equally often in each condition, and every
  participant has K/2 trials per condition.
* Within a participant, conditions alternate trial by trial (R V R V ... or V R V R ...) so that
  condition is never confounded with fatigue/learning; the starting condition alternates across twin
  blocks (and is opposite between twins), and pair order within condition is random.
* Which unit of a pair is presented first (``unit_a``) is randomised per trial.
* Every report trial carries one probability probe; the probed dimension rotates over
  quiet/sunny/cool.

CLI::

    python -m study.randomize --n-participants 24 --units-file study/data/units_truth.csv \
        --k 6 --seed 20261024 --out study/data/schedule.csv
    python -m study.randomize --participants P01 P02 ... --units U01 U02 U03 U04 --consent-d-confirmed
    python -m study.randomize ... --pairs my_pairs.csv     # columns pair_id,unit_a,unit_b
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from study.schema import DATA, DIMS, SCHEDULE_COLS

DEFAULT_SEED = 20261024


def all_pairs(units: list[str]) -> pd.DataFrame:
    rows = [{"pair_id": f"{a}-{b}", "unit_a": a, "unit_b": b} for a, b in itertools.combinations(units, 2)]
    return pd.DataFrame(rows)


def make_schedule(participants: list[str], pairs: pd.DataFrame, k: int, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    if k % 2:
        raise ValueError("K must be even (half video-only, half report)")
    if len(pairs) < k:
        raise ValueError(f"need at least K={k} distinct pairs, have {len(pairs)} (add units to the pool)")
    if pairs["pair_id"].duplicated().any():
        raise ValueError("duplicate pair_id")
    rng = np.random.default_rng(seed)
    pair_ids = pairs["pair_id"].tolist()
    units = pairs.set_index("pair_id")[["unit_a", "unit_b"]]
    exposure = dict.fromkeys(pair_ids, 0)
    rows = []
    for b, start in enumerate(range(0, len(participants), 2)):
        twins = participants[start : start + 2]
        # choose K least-exposed pairs (random tie-break)
        jitter = rng.random(len(pair_ids))
        order = sorted(range(len(pair_ids)), key=lambda i: (exposure[pair_ids[i]], jitter[i]))
        chosen = [pair_ids[i] for i in order[:k]]
        for pid in chosen:
            exposure[pid] += len(twins)
        perm = rng.permutation(chosen).tolist()
        split = {"report": perm[: k // 2], "video": perm[k // 2 :]}
        first = "report" if b % 2 == 0 else "video"
        for t_i, part in enumerate(twins):
            cond_sets = split if t_i == 0 else {"report": split["video"], "video": split["report"]}
            start_c = first if t_i == 0 else ("video" if first == "report" else "report")
            other = "video" if start_c == "report" else "report"
            seq_a = rng.permutation(cond_sets[start_c]).tolist()
            seq_b = rng.permutation(cond_sets[other]).tolist()
            p_index = start + t_i
            n_rep = 0
            for trial in range(k):
                cond = start_c if trial % 2 == 0 else other
                pair = seq_a[trial // 2] if trial % 2 == 0 else seq_b[trial // 2]
                ua, ub = units.loc[pair, "unit_a"], units.loc[pair, "unit_b"]
                if rng.random() < 0.5:
                    ua, ub = ub, ua
                probe = cond == "report"
                dim = DIMS[(p_index + n_rep) % len(DIMS)] if probe else ""
                n_rep += int(probe)
                rows.append(
                    {
                        "participant_id": part,
                        "trial": trial + 1,
                        "pair_id": pair,
                        "unit_a": ua,
                        "unit_b": ub,
                        "condition": cond,
                        "probe": probe,
                        "probe_dim": dim,
                        "schedule_seed": seed,
                    }
                )
    return pd.DataFrame(rows, columns=SCHEDULE_COLS)


def balance_report(s: pd.DataFrame) -> dict:
    by_pair = s.groupby(["pair_id", "condition"]).size().unstack(fill_value=0)
    by_part = s.groupby(["participant_id", "condition"]).size().unstack(fill_value=0)
    first = s[s["trial"] == 1]["condition"].value_counts().to_dict()
    pos = s.groupby(["trial", "condition"]).size().unstack(fill_value=0)
    return {
        "max_pair_condition_imbalance": int((by_pair.get("report", 0) - by_pair.get("video", 0)).abs().max()),
        "participants_with_unequal_split": int((by_part.get("report", 0) != by_part.get("video", 0)).sum()),
        "first_trial_condition_counts": {str(k): int(v) for k, v in first.items()},
        "max_position_condition_imbalance": int((pos.get("report", 0) - pos.get("video", 0)).abs().max()),
        "pair_exposure_range": [
            int(s["pair_id"].value_counts().min()),
            int(s["pair_id"].value_counts().max()),
        ],
        "probe_dim_counts": {str(k): int(v) for k, v in s.loc[s["probe"], "probe_dim"].value_counts().items()},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--participants", nargs="+", help="pseudonymous participant IDs, e.g. P01 P02 ...")
    g.add_argument("--n-participants", type=int, help="generate IDs P01..PNN")
    u = ap.add_mutually_exclusive_group(required=True)
    u.add_argument("--units", nargs="+", help="pool unit IDs (requires --consent-d-confirmed)")
    u.add_argument("--units-file", type=Path, help="units_truth.csv (uses its consent_d column)")
    ap.add_argument(
        "--consent-d-confirmed",
        action="store_true",
        help="confirm every unit passed with --units has signed consent code D",
    )
    ap.add_argument("--pairs", type=Path, help="optional CSV pair_id,unit_a,unit_b (default: all pairs)")
    ap.add_argument("--k", type=int, default=6, help="pairs per participant (even)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=DATA / "schedule.csv")
    ap.add_argument("--force", action="store_true", help="overwrite an existing schedule")
    a = ap.parse_args(argv)

    if a.units_file is not None:
        t = pd.read_csv(a.units_file, dtype={"unit_id": str})
        ok = t["consent_d"].astype(str).str.lower().isin({"1", "true", "yes", "y"})
        if not ok.all():
            print(f"refusing: units without consent D: {t.loc[~ok, 'unit_id'].tolist()}", file=sys.stderr)
            return 2
        units = t["unit_id"].tolist()
    else:
        if not a.consent_d_confirmed:
            print("refusing: pass --consent-d-confirmed (every unit must have consent code D)", file=sys.stderr)
            return 2
        units = list(a.units)
    if len(units) < 4:
        print(f"refusing: pool needs >= 4 consented units, got {len(units)}", file=sys.stderr)
        return 2
    pairs = pd.read_csv(a.pairs, dtype=str) if a.pairs else all_pairs(units)
    if not set(pairs["unit_a"]).union(pairs["unit_b"]) <= set(units):
        print("refusing: pair list references units outside the consented pool", file=sys.stderr)
        return 2
    parts = a.participants or [f"P{i:02d}" for i in range(1, a.n_participants + 1)]
    if a.out.exists() and not a.force:
        print(
            f"refusing to overwrite {a.out} (use --force; the schedule should be fixed before session 1)",
            file=sys.stderr,
        )
        return 2
    s = make_schedule(parts, pairs, a.k, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    s.to_csv(a.out, index=False)
    print(f"wrote {a.out} ({len(parts)} participants x {a.k} pairs, seed {a.seed})")
    for k_, v in balance_report(s).items():
        print(f"  {k_}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
