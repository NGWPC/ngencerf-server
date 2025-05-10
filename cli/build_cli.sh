#!/usr/bin/env bash
set -euo pipefail

# Move to script directory
cd "$(dirname "$0")"

APP_NAME="ngencerf"
ENTRY_POINT="ngencerf/run_cli.py"
BUILD_VENV=".venv-build"

cleanup() {
  echo "==> Cleaning up..."
  deactivate || true
  rm -rf "$BUILD_VENV" ngencerf.spec build/
}

trap cleanup EXIT

echo "==> Creating build virtual environment..."
python3 -m venv "$BUILD_VENV"
source "$BUILD_VENV/bin/activate"

echo "==> Upgrading pip and installing PyInstaller..."
python3 -m pip install --upgrade pip
pip install pyinstaller

echo "==> Installing build dependencies from pyproject.toml..."
pip install -e .

echo "Virtual environment: $VIRTUAL_ENV"

echo "==> Running PyInstaller..."
if ! pyinstaller --onefile \
  --name "$APP_NAME" \
  --strip \
  "$ENTRY_POINT"; then
  echo "❌ PyInstaller build failed."
  exit 1
fi

echo "==> Build complete. Executable located at: dist/$APP_NAME"
