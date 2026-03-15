#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_ROOT="$PROJECT_ROOT/deploy/ubuntu"
BUILD_ROOT="$OUTPUT_ROOT/build"
RELEASE_ROOT="$OUTPUT_ROOT/AttendanceWidget"
CACHE_ROOT="$OUTPUT_ROOT/.nuitka-cache"
BUILD_VENV="$OUTPUT_ROOT/.build-venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_PYTHON="$BUILD_VENV/bin/python"
BUILD_PIP="$BUILD_VENV/bin/pip"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -d "$BUILD_VENV" ]]; then
  "$PYTHON_BIN" -m venv "$BUILD_VENV"
fi

"$BUILD_PYTHON" -m pip install --upgrade pip setuptools wheel
"$BUILD_PIP" install -e "$PROJECT_ROOT"
"$BUILD_PIP" install nuitka ordered-set zstandard

"$BUILD_PYTHON" "$PROJECT_ROOT/tools/sync_assets.py"

rm -rf "$BUILD_ROOT" "$RELEASE_ROOT"
mkdir -p "$OUTPUT_ROOT" "$CACHE_ROOT"
export NUITKA_CACHE_DIR="$CACHE_ROOT"

pushd "$PROJECT_ROOT" >/dev/null
"$BUILD_PYTHON" -m nuitka   --standalone   --assume-yes-for-downloads   --enable-plugin=pyside6   --output-dir="$BUILD_ROOT"   --output-filename=AttendanceWidget   --include-data-dir=assets=assets   --include-package=selenium.webdriver.chrome   --include-package=selenium.webdriver.chromium   --include-data-file=.env.example=.env.example   --include-data-file=README.md=README.md   main.py
popd >/dev/null

DIST_DIR="$BUILD_ROOT/main.dist"
if [[ ! -d "$DIST_DIR" ]]; then
  echo "Nuitka output not found: $DIST_DIR" >&2
  exit 1
fi

mv "$DIST_DIR" "$RELEASE_ROOT"
cp "$OUTPUT_ROOT/README.txt" "$RELEASE_ROOT/README.txt"
cat > "$RELEASE_ROOT/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$SELF_DIR/AttendanceWidget.bin" ]]; then
  exec "$SELF_DIR/AttendanceWidget.bin"
fi
if [[ -x "$SELF_DIR/AttendanceWidget" ]]; then
  exec "$SELF_DIR/AttendanceWidget"
fi
if [[ -x "$SELF_DIR/main.bin" ]]; then
  exec "$SELF_DIR/main.bin"
fi
if [[ -x "$SELF_DIR/main" ]]; then
  exec "$SELF_DIR/main"
fi
echo "Executable not found in $SELF_DIR" >&2
exit 1
EOF
chmod +x "$RELEASE_ROOT/run.sh"
chmod +x "$OUTPUT_ROOT/build.sh"
echo "Ubuntu release created at $RELEASE_ROOT"
echo "Run: $RELEASE_ROOT/run.sh"
