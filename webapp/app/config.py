import os
from pathlib import Path

WEBAPP = Path(__file__).resolve().parents[1]
ROOT = WEBAPP.parent

ARTIFACTS = Path(os.environ.get("ARTIFACTS_DIR", ROOT / "data" / "model_artifacts"))
LIVE_DIR = Path(os.environ.get("LIVE_DIR", WEBAPP / "data" / "live"))
CONTENT_DIR = Path(os.environ.get("CONTENT_DIR", WEBAPP / "content"))
STATIC_DIR = WEBAPP / "static"
SEED_PRICE_TSV = Path(os.environ.get("SEED_PRICE_TSV", ROOT / "data" / "coin_metrics.tsv"))

SEQ_LEN = 20
CLIP_VAL = 5.0
HORIZONS = [1, 3, 5, 7, 15, 20, 25, 30, 35]
MH_SEEDS = [47, 123, 2024]
