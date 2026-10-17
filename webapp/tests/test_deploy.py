from pathlib import Path

import pytest
import yaml

from app import config

WEBAPP = config.WEBAPP
DEPLOY = WEBAPP / "deploy_artifacts"
WORKFLOW = WEBAPP / "deploy" / "daily-update.yml"


def test_deploy_artifacts_are_small_and_complete():
    names = ["scaler.pkl", "threshold_beku.json", "coin_metrics.tsv", "models/model_F.keras", "multihorizon/thresholds.json"]
    names += [f"multihorizon/F_h{h}_s{s}.keras" for h in config.HORIZONS[1:] for s in config.MH_SEEDS]
    for n in names:
        assert (DEPLOY / n).exists(), n
    assert sum(f.stat().st_size for f in DEPLOY.rglob("*") if f.is_file()) < 40_000_000
    assert max(f.stat().st_size for f in DEPLOY.rglob("*") if f.is_file()) < 50_000_000       # batas GitHub: 100 MB/berkas


@pytest.mark.slow
def test_predictor_loads_every_horizon_from_deploy_artifacts():
    from app.inference import Predictor
    pred = Predictor.from_artifacts(DEPLOY)
    assert sorted(pred.models) == sorted(config.HORIZONS)                  # mh dilewati diam-diam bila berkas kurang


def load_workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_runs_daily_and_manually_with_least_privilege():
    wf = load_workflow()
    on = wf.get("on") or wf[True]                                          # PyYAML membaca kunci 'on' sebagai True
    assert on["schedule"][0]["cron"].split()[2:] == ["*", "*", "*"] and "workflow_dispatch" in on
    assert wf["permissions"] == {"contents": "write"}
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_workflow_uses_secrets_never_literals_and_pins_artifacts():
    text = WORKFLOW.read_text()
    for key in ("ANTHROPIC_API_KEY", "COINDESK_API_KEY"):
        assert f"{key}: ${{{{ secrets.{key} }}}}" in text
    assert "sk-ant" not in text
    step_runs = " ".join(s.get("run", "") for s in load_workflow()["jobs"]["update"]["steps"])
    assert "python -m app.jobs" in step_runs and "python -m scripts.export_static" in step_runs
    assert "ARTIFACTS_DIR" in text and "SEED_PRICE_TSV" in text and "deploy_artifacts" in text


def test_workflow_stops_before_publishing_when_job_fails():
    steps = load_workflow()["jobs"]["update"]["steps"]
    order = [s.get("name", "") for s in steps]
    assert order.index("Job harian (model, berita, sentimen)") < order.index("Ekspor situs statis") < order.index("Publikasi ke gh-pages")
    assert not any(s.get("continue-on-error") for s in steps)


def test_live_state_is_tracked_but_backups_are_not():
    ignore = (WEBAPP / ".gitignore").read_text().splitlines()
    assert "data/live/" not in ignore
    assert "data/live/_*/" in ignore
