#!/usr/bin/env bash
# Convert a HuggingFace Whisper checkpoint to whisper.cpp GGML and install it
# into voxd's models dir.
#
# Usage:
#   ./add-hf-model.sh <hf-repo> <local-name> [--quantize q5_0|q8_0]
#
# Example:
#   ./add-hf-model.sh antony66/whisper-large-v3-russian large-v3-ru
#   ./add-hf-model.sh antony66/whisper-large-v3-russian large-v3-ru --quantize q5_0
#
# Result: ~/.local/share/voxd/models/ggml-<local-name>.bin (and a -q5_0 variant
# if --quantize is passed).
#
# Prereqs: git, git-lfs, python3 with torch+transformers (installed into .venv),
#          whisper.cpp checked out + built (./setup.sh handles that).
set -euo pipefail

if [[ $# -lt 2 ]]; then
  sed -n '2,16p' "$0"
  exit 2
fi

HF_REPO="$1"
LOCAL_NAME="$2"
shift 2
QUANT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quantize) QUANT="${2:?missing arg to --quantize}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
WHISPER_CPP="$SCRIPT_DIR/whisper.cpp"
MODELS_OUT="${XDG_DATA_HOME:-$HOME/.local/share}/voxd/models"
WORK_DIR="$(mktemp -d -t voxd-hf-XXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

# ── checks ───────────────────────────────────────────────────────────────────
[[ -x "$VENV_DIR/bin/python" ]] || { echo "error: .venv missing — run ./dev-gui.sh --no-run first" >&2; exit 1; }
[[ -d "$WHISPER_CPP" ]]         || { echo "error: $WHISPER_CPP missing — run ./setup.sh first" >&2; exit 1; }
command -v git-lfs >/dev/null   || { echo "error: install git-lfs first (sudo apt/dnf install git-lfs && git lfs install)" >&2; exit 1; }

CONVERT_SCRIPT="$WHISPER_CPP/models/convert-h5-to-ggml.py"
[[ -f "$CONVERT_SCRIPT" ]] || { echo "error: $CONVERT_SCRIPT not found in your whisper.cpp checkout" >&2; exit 1; }

# ── ensure conversion deps in venv ───────────────────────────────────────────
echo "==> Ensuring torch + transformers in .venv (one-time)"
"$VENV_DIR/bin/pip" install --quiet torch transformers

# ── fetch HF checkpoint ──────────────────────────────────────────────────────
HF_DIR="$WORK_DIR/hf-model"
echo "==> Cloning $HF_REPO → $HF_DIR"
GIT_LFS_SKIP_SMUDGE=0 git clone --depth 1 "https://huggingface.co/$HF_REPO" "$HF_DIR"

# ── fetch OpenAI whisper repo (convert-h5-to-ggml.py needs its tokenizer/asset files) ──
WHISPER_PY="$WORK_DIR/whisper-openai"
echo "==> Cloning openai/whisper (for tokenizer/assets)"
git clone --depth 1 https://github.com/openai/whisper "$WHISPER_PY"

# ── convert ──────────────────────────────────────────────────────────────────
CONV_OUT="$WORK_DIR/converted"
mkdir -p "$CONV_OUT"
echo "==> Converting HF → GGML (this allocates the full model in RAM)"
"$VENV_DIR/bin/python" "$CONVERT_SCRIPT" "$HF_DIR" "$WHISPER_PY" "$CONV_OUT" 1

mkdir -p "$MODELS_OUT"
DEST="$MODELS_OUT/ggml-$LOCAL_NAME.bin"
mv "$CONV_OUT/ggml-model.bin" "$DEST"
echo "==> Installed: $DEST"

# ── optional quantization ────────────────────────────────────────────────────
if [[ -n "$QUANT" ]]; then
  QBIN="$WHISPER_CPP/build/bin/quantize"
  [[ -x "$QBIN" ]] || { echo "warn: $QBIN not built; skipping quantize" >&2; exit 0; }
  QDEST="$MODELS_OUT/ggml-$LOCAL_NAME-$QUANT.bin"
  echo "==> Quantizing to $QUANT → $QDEST"
  "$QBIN" "$DEST" "$QDEST" "$QUANT"
  echo "==> Installed: $QDEST"
fi

echo
echo "Activate via GUI Model Manager, OR edit ~/.config/voxd/config.yaml:"
echo "  whisper_model_path: $DEST"
echo "  language: ru   # this checkpoint is Russian-only"
