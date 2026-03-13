#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"
DIST_DIR="$SCRIPT_DIR/dist"
BIN_PATH="$DIST_DIR/AttendanceWidget.bin"
VENV_DIR="$APP_DIR/.venv"

if [ -x "$BIN_PATH" ]; then
  exec "$BIN_PATH"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install "$APP_DIR"
fi

cd "$APP_DIR"
exec "$VENV_DIR/bin/python" main.py
