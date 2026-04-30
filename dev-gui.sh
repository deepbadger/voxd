#!/usr/bin/env bash
# Dev helper: (re)create .venv and launch `voxd --gui`.
#
# Usage:
#   ./dev-gui.sh                # create venv if missing, ensure deps, run GUI
#   ./dev-gui.sh --rebuild      # delete .venv and recreate it from scratch
#   ./dev-gui.sh -- --tray      # forward args to voxd (here: launch tray instead)
#   ./dev-gui.sh --no-run       # set up venv but don't launch the app
#
# Requires: python3 (>=3.9), pip, system libs for PyQt6 + sounddevice
# (libportaudio2 on Debian/Ubuntu, portaudio on Arch/Fedora).
# whisper-cli is NOT built here; `voxd` will prompt to build it on first run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PY_BIN="${PY_BIN:-python3}"
REBUILD=0
RUN_APP=1
PASSTHRU_ARGS=()

# ── argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild) REBUILD=1; shift ;;
    --no-run)  RUN_APP=0; shift ;;
    --) shift; PASSTHRU_ARGS=("$@"); break ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0 ;;
    *)
      echo "Unknown flag: $1 (use '-- ARG ARG' to forward args to voxd)" >&2
      exit 2 ;;
  esac
done

# Default voxd args = --gui
if [[ ${#PASSTHRU_ARGS[@]} -eq 0 ]]; then
  PASSTHRU_ARGS=(--gui)
fi

# ── sanity checks ────────────────────────────────────────────────────────────
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "error: $PY_BIN not found on PATH" >&2
  exit 1
fi

PY_VER=$("$PY_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "==> Using $PY_BIN ($PY_VER)"

# ── detect broken venv (e.g. dangling symlinks from old uv install) ──────────
venv_is_broken() {
  [[ -d "$VENV_DIR" ]] || return 1
  [[ ! -x "$VENV_DIR/bin/python" ]] && return 0
  "$VENV_DIR/bin/python" -c 'import sys' >/dev/null 2>&1 || return 0
  return 1
}

if [[ "$REBUILD" -eq 1 ]] || venv_is_broken; then
  if [[ -d "$VENV_DIR" ]]; then
    echo "==> Removing existing venv at $VENV_DIR"
    rm -rf "$VENV_DIR"
  fi
fi

# ── create venv if missing ───────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
  echo "==> Creating venv at $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── install deps + voxd in editable mode (idempotent) ────────────────────────
PIP="$VENV_DIR/bin/pip"
"$PIP" install --upgrade pip wheel >/dev/null

# Marker so we don't re-resolve dependencies on every launch.
STAMP="$VENV_DIR/.voxd-installed"
PYPROJECT_MTIME=$(stat -c %Y pyproject.toml 2>/dev/null || stat -f %m pyproject.toml)
NEED_INSTALL=1
if [[ -f "$STAMP" ]] && [[ "$(cat "$STAMP")" == "$PYPROJECT_MTIME" ]]; then
  NEED_INSTALL=0
fi

if [[ "$NEED_INSTALL" -eq 1 ]]; then
  echo "==> Installing voxd (editable) and dependencies"
  "$PIP" install -e .
  echo "$PYPROJECT_MTIME" > "$STAMP"
else
  echo "==> Dependencies already installed (pyproject.toml unchanged)"
fi

# ── run ──────────────────────────────────────────────────────────────────────
if [[ "$RUN_APP" -eq 0 ]]; then
  echo "==> Setup complete. Activate with: source $VENV_DIR/bin/activate"
  exit 0
fi

echo "==> Launching: voxd ${PASSTHRU_ARGS[*]}"
exec "$VENV_DIR/bin/voxd" "${PASSTHRU_ARGS[@]}"
