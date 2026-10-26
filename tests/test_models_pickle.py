"""The trained model bundle is pickled by `make train`; an unfitted prior must already round-trip."""

import pickle

import numpy as np

from hybrid.priors import HiddenPropertyModel


def test_hidden_property_model_pickles() -> None:
    m = HiddenPropertyModel()
    m.c_g[("pre1960", "lowrise")] += 1.0
    m2 = pickle.loads(pickle.dumps(m))
    assert np.allclose(m2.c_g[("pre1960", "lowrise")], m.c_g[("pre1960", "lowrise")])
    assert m2.c_w["unseen"].sum() == 0.0
