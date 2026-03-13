#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"
BUILD_VENV="$SCRIPT_DIR/.build-venv"
DIST_DIR="$SCRIPT_DIR/dist"

python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip install \
  "PySide6>=6.9.0" \
  "python-dotenv>=1.1.0" \
  "selenium>=4.31.0" \
  nuitka ordered-set zstandard

"$BUILD_VENV/bin/python" -m nuitka \
  --standalone \
  --enable-plugin=pyside6 \
  --assume-yes-for-downloads \
  --output-dir="$DIST_DIR" \
  --output-filename=AttendanceWidget \
  --include-data-files="$SCRIPT_DIR/koverwatch.ttf=koverwatch.ttf" \
  --include-data-files="$SCRIPT_DIR/overwatch_blue_new.png=overwatch_blue_new.png" \
  --include-data-files="$SCRIPT_DIR/overwatch_red_new.png=overwatch_red_new.png" \
  "$APP_DIR/main.py"

find "$DIST_DIR" -maxdepth 2 -type f -name 'AttendanceWidget.bin' -print
