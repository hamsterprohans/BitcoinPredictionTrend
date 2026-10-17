import subprocess
from pathlib import Path

import pytest

from app import config
from scripts.publish_site import REPO_URL, publish


class Recorder:
    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on

    def __call__(self, args, cwd=None, **kw):
        self.calls.append((list(args), str(cwd) if cwd else None))
        if self.fail_on and self.fail_on in " ".join(args):
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def cmds(rec):
    return [" ".join(a) for a, _ in rec.calls]


def test_runs_job_then_export_then_saves_state_then_force_pushes_gh_pages(tmp_path):
    rec = Recorder()
    publish(run=rec, out=tmp_path / "dist", python="py")
    c = cmds(rec)
    i_job = next(i for i, x in enumerate(c) if "app.jobs" in x)
    i_exp = next(i for i, x in enumerate(c) if "scripts.export_static" in x)
    i_push = next(i for i, x in enumerate(c) if "push" in x and "gh-pages" in x)
    assert i_job < i_exp < i_push
    assert any("--base /BitcoinPredictionTugasAkhir" in x for x in c)         # subpath situs dari nama repo
    assert "--force" in c[i_push] and REPO_URL in c[i_push]
    assert any(x.startswith("git add data/live") for x in c)                  # keadaan harian disimpan


def test_failed_job_stops_before_export_and_publish(tmp_path):
    rec = Recorder(fail_on="app.jobs")
    with pytest.raises(SystemExit) as e:
        publish(run=rec, out=tmp_path / "dist", python="py")
    assert "job harian" in str(e.value).lower()
    assert not any("export_static" in x or "push" in x for x in cmds(rec))


def test_failed_export_stops_before_publish(tmp_path):
    rec = Recorder(fail_on="export_static")
    with pytest.raises(SystemExit):
        publish(run=rec, out=tmp_path / "dist", python="py")
    assert not any("push" in x for x in cmds(rec))


def test_skip_job_flag_only_exports_and_publishes(tmp_path):
    rec = Recorder()
    publish(run=rec, out=tmp_path / "dist", python="py", skip_job=True)
    assert not any("app.jobs" in x for x in cmds(rec)) and any("push" in x for x in cmds(rec))


def test_timer_units_run_daily_after_utc_close_and_catch_up_missed_runs():
    d = config.WEBAPP / "deploy"
    timer = (d / "btc-publish.timer").read_text()
    assert "OnCalendar=*-*-* 03:00:00 UTC" in timer and "Persistent=true" in timer
    service = (d / "btc-publish.service").read_text()
    assert "scripts.publish_site" in service and "@WEBAPP@" in service      # jalur diisi oleh install-timer.sh
    assert 'ExecStart="@WEBAPP@/.venv/bin/python"' in service                # path berspasi harus dikutip
    assert (d / "install-timer.sh").read_text().startswith("#!/usr/bin/env bash")
