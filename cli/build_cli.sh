#!/usr/bin/env bash
set -euo pipefail

# Move to script directory
cd "$(dirname "$0")"

APP_NAME="ngencerf"
ENTRY_POINT="ngencerf/run_cli.py"
BUILD_VENV=".venv-build"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"

PYINSTALLER_PLATFORM_ARGS=()

case "$OS_NAME" in
  Linux)
    PLATFORM_DIR="linux"
    ;;
  Darwin)
    PLATFORM_DIR="macos"
    PYINSTALLER_PLATFORM_ARGS+=(--target-arch x86_64)
    ;;
  *)
    echo "ERROR: Unsupported OS: $OS_NAME"
    echo "This script supports Linux and macOS only."
    exit 1
    ;;
esac

cleanup() {
  echo "==> Cleaning up..."
  command -v deactivate &>/dev/null && deactivate || true
  rm -rf "$BUILD_VENV" ngencerf.spec build/
}

trap cleanup EXIT

echo "==> Building $APP_NAME for $PLATFORM_DIR ($ARCH_NAME)..."

#=======================================================================
# Verify CLI and server enums are in sync before building
#=======================================================================
# NOTE:
# This build step assumes we are executing from inside the CLI directory:
#     /ngencerf/ngencerf-server/cli
#
# That’s the default Docker build context (RUN cli/build_cli.sh).
# If the script is ever run manually from another directory, relative paths
# to `check_enum_consistency.py` will not resolve correctly.
#
# To prevent path errors, we reference the file explicitly as "./check_enum_consistency.py"
# and fail fast if it's missing.
#=======================================================================
echo "==> Checking CalibrationSortField consistency..."

if [[ ! -f "./check_enum_consistency.py" ]]; then
    echo "Error: check_enum_consistency.py not found in $(pwd)"
    echo "This script must be run from the CLI directory."
    exit 1
fi

python "./check_enum_consistency.py" || {
    echo "Enum consistency check failed. Fix mismatch before building."
    exit 1
}

cleanup

echo "==> Creating build virtual environment..."
python -m venv "$BUILD_VENV"
source "$BUILD_VENV/bin/activate"

if [[ "$OS_NAME" == "Darwin" ]]; then
  PYTHON_ARCH="$(python -c 'import platform; print(platform.machine())')"

  if [[ "$PYTHON_ARCH" != "x86_64" ]]; then
    echo "WARNING: macOS Intel build requested, but active Python reports architecture: $PYTHON_ARCH"
    echo "For the most reliable Intel-compatible macOS build, run this script with an x86_64 Python under Rosetta."
    echo "The build will continue, but verify the result with:"
    echo "  file ../downloads/latest/macos/$APP_NAME"
  fi
fi

echo "==> Upgrading pip and installing PyInstaller..."
python -m pip install --upgrade pip
python -m pip install pyinstaller

echo "==> Installing build dependencies from pyproject.toml..."
python -m pip install .

echo "Virtual environment: $VIRTUAL_ENV"

# CLI git info (ngencerf/git_info.json), embedded via --add-data below and read at
# runtime by `ngencerf version` / `ngencerf about`. Two paths reach this point:
#
#   1. Linux CI build: this script runs INSIDE the manylinux2014 container, which has
#      no jq and not the full git checkout. The workflow already ran gen_git_info.sh
#      on the host beforehand, so git_info.json exists -> reuse it in the if block. The
#      container must NOT try to regenerate, or the jq call would fail the build.
#
#   2. macOS CI build and any standalone/local run: nothing pre-generated it, so the
#      `else` generates it now. jq + git are present in these environments. This is
#      exactly what build_cli.sh did before the Linux build moved into the container,
#      so standalone behavior is unchanged.
#
# The `else` is what keeps a plain `bash cli/build_cli.sh` self-contained; without it,
# only the Linux-CI path (which pre-generates on the host) would produce git info.
if [[ -f ngencerf/git_info.json ]]; then
  echo "==> Reusing ngencerf/git_info.json generated earlier on the host"
else
  bash ./gen_git_info.sh
fi

echo "==> Running PyInstaller..."

if ! pyinstaller --onefile \
  --name "$APP_NAME" \
  "${PYINSTALLER_PLATFORM_ARGS[@]}" \
  --add-data "ngencerf/git_info.json:ngencerf" \
  "$ENTRY_POINT"; then
  echo "❌ PyInstaller build failed."
  exit 1
fi

mkdir -p "../downloads/latest/$PLATFORM_DIR"

cp "dist/$APP_NAME" \
   "../downloads/latest/$PLATFORM_DIR/$APP_NAME"

echo "==> Build complete. Executable located at: ../downloads/latest/$PLATFORM_DIR/$APP_NAME"

if [[ "$OS_NAME" == "Darwin" ]]; then
  echo "==> macOS executable architecture:"
  file "../downloads/latest/$PLATFORM_DIR/$APP_NAME"
fi