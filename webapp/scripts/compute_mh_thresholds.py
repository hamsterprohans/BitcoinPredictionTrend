"""Hitung threshold per horizon = Youden dari rata-rata probabilitas validasi Model C (3 seed).

Pemakaian: python -m scripts.compute_mh_thresholds
Butuh <ARTIFACTS>/multihorizon/C_h{H}_s{seed}.npz (dari notebook sel M1).
"""
import json
from pathlib import Path

import numpy as np

from app import config
from app.inference import youden_threshold


def compute(artifacts: Path, horizons=None, seeds=None) -> dict:
    horizons = horizons or config.HORIZONS[1:]
    seeds = seeds or config.MH_SEEDS
    mh = Path(artifacts) / "multihorizon"
    if not mh.is_dir():
        return {}
    out = {}
    for h in horizons:
        files = [mh / f"C_h{h}_s{s}.npz" for s in seeds]
        if not all(f.exists() for f in files):
            continue
        data = [np.load(f) for f in files]
        pv = np.mean([d["pv"] for d in data], axis=0)
        out[str(h)] = youden_threshold(data[0]["yv"], pv)
    (mh / "thresholds.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    res = compute(config.ARTIFACTS)
    if not (config.ARTIFACTS / "multihorizon").is_dir():
        raise SystemExit(f"Folder {config.ARTIFACTS / 'multihorizon'} belum ada. Ekspor dari notebook (10) dulu "
                         "(lihat README bagian 'Ekspor artefak dari notebook (10)'); tanpa itu hanya prediksi 1 hari yang tampil.")
    print("threshold per horizon:", res)
    missing = [h for h in config.HORIZONS[1:] if str(h) not in res]
    if missing:
        print("BELUM ADA berkas C_h*_s*.npz untuk horizon:", missing)
