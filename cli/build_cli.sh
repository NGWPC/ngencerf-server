#!/usr/bin/env bash
set -euo pipefail

# Move to script directory
cd "$(dirname "$0")"

APP_NAME="ngencerf"
ENTRY_POINT="ngencerf/run_cli.py"
BUILD_VENV=".venv-build"

echo "==> Creating build virtual environment..."
python3 -m venv "$BUILD_VENV"
source "$BUILD_VENV/bin/activate"

echo "==> Installing build dependencies from pyproject.toml..."
pip install --upgrade pip
pip install .

echo "==> Running PyInstaller..."
pyinstaller --onefile \
  --name "$APP_NAME" \
  --strip \
  --paths=ngencerf \
  "$ENTRY_POINT"

echo "==> Build complete. Executable located at: dist/$APP_NAME"


