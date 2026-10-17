"""Pembaruan harian dari komputer sendiri: job (model, berita, sentimen) -> ekspor situs -> publikasi ke gh-pages.

Pemakaian: python -m scripts.publish_site [--skip-job]
Dijalankan terjadwal lewat deploy/install-timer.sh (systemd). Alternatif bila GitHub Actions tidak tersedia.
Bila job atau ekspor gagal, situs yang sedang tayang tidak disentuh.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from app import config

REPO_URL = "https://github.com/hanscakrawangsa15/BitcoinPredictionTugasAkhir.git"


def _step(run, label, args, cwd=None):
    try:
        run(args, cwd=cwd, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"{label} gagal (kode {e.returncode}); situs yang tayang tidak diubah.") from e


def publish(run=subprocess.run, out: Path | None = None, python: str = sys.executable, skip_job: bool = False,
            repo_url: str = REPO_URL) -> None:
    out = Path(out) if out else Path(tempfile.mkdtemp(prefix="btc-site-"))
    base = "/" + repo_url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    web = config.WEBAPP
    if not skip_job:
        _step(run, "Job harian", [python, "-m", "app.jobs"], cwd=web)
    _step(run, "Ekspor situs", [python, "-m", "scripts.export_static", "--base", base, "--out", str(out)], cwd=web)
    if not skip_job:                                   # simpan keadaan harian di git lokal (abaikan bila tak ada perubahan)
        run(["git", "add", "data/live"], cwd=web, check=False)
        _commit_state(run, web)
    _step(run, "Inisialisasi publikasi", ["git", "init", "-q", "-b", "gh-pages"], cwd=out)
    _step(run, "Commit publikasi", ["git", "add", "-A"], cwd=out)
    _step(run, "Commit publikasi", ["git", "-c", "user.name=btc-publish", "-c", "user.email=btc-publish@localhost",
                                    "commit", "-q", "-m", "Publikasi situs statis (harian)"], cwd=out)
    _step(run, "Push gh-pages", ["git", "push", "--force", repo_url, "gh-pages"], cwd=out)
    print(f"Situs diperbarui: https://hanscakrawangsa15.github.io{base}/", file=sys.stderr)


def _commit_state(run, web):
    staged = run(["git", "diff", "--cached", "--quiet"], cwd=web, check=False)
    if getattr(staged, "returncode", 0) != 0:
        run(["git", "commit", "-q", "-m", "data: pembaruan harian"], cwd=web, check=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-job", action="store_true", help="lewati job harian; hanya ekspor dan publikasikan data yang ada")
    publish(skip_job=ap.parse_args().skip_job)
