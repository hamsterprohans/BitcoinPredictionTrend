#!/usr/bin/env bash
# Unduh three.js, lightweight-charts, dan font Geist ke static/. Jalankan sekali; hasilnya di-commit.
set -euo pipefail
cd "$(dirname "$0")/../static"
mkdir -p vendor fonts
J="https://cdn.jsdelivr.net/npm"
curl -fsSL "$J/three@0.170.0/build/three.module.min.js" -o vendor/three.module.min.js
curl -fsSL "$J/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js" -o vendor/lightweight-charts.standalone.production.js
curl -fsSL "$J/geist@1.3.1/dist/fonts/geist-sans/Geist-Variable.woff2" -o fonts/Geist-Variable.woff2
curl -fsSL "$J/geist@1.3.1/dist/fonts/geist-mono/GeistMono-Variable.woff2" -o fonts/GeistMono-Variable.woff2
ls -l vendor fonts
