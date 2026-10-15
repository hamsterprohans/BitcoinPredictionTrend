import json

import numpy as np

from scripts.compute_mh_thresholds import compute


def test_youden_from_mean_of_seed_probabilities(tmp_path):
    mh = tmp_path / "multihorizon"
    mh.mkdir()
    rng = np.random.default_rng(0)
    yv = rng.integers(0, 2, 200)
    for s in (47, 123, 2024):
        pv = np.clip(0.5 + (yv - 0.5) * 0.3 + rng.normal(0, 0.1, 200), 0, 1)
        np.savez(mh / f"C_h3_s{s}.npz", pv=pv, pt=pv, yv=yv, yt=yv, base_tr=0.5)
    out = compute(tmp_path, horizons=[3, 5], seeds=[47, 123, 2024])
    assert set(out) == {"3"}            # H=5 tidak punya berkas -> dilewati
    assert 0.3 < out["3"] < 0.7
    assert json.loads((mh / "thresholds.json").read_text()) == out


def test_missing_multihorizon_folder_is_not_a_crash(tmp_path):
    assert compute(tmp_path) == {}
    assert not (tmp_path / "multihorizon").exists()          # tidak membuat folder kosong diam-diam
