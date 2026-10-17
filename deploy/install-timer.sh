#!/usr/bin/env bash
# Memasang timer systemd (tingkat pengguna) untuk pembaruan harian. Pemakaian: bash deploy/install-timer.sh
# Lepas: systemctl --user disable --now btc-publish.timer
set -euo pipefail
WEBAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"
sed "s|@WEBAPP@|$WEBAPP|g" "$WEBAPP/deploy/btc-publish.service" > "$DEST/btc-publish.service"
cp "$WEBAPP/deploy/btc-publish.timer" "$DEST/btc-publish.timer"
systemctl --user daemon-reload
systemctl --user enable --now btc-publish.timer
systemctl --user list-timers btc-publish.timer --no-pager
