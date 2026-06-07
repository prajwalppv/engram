#!/bin/bash
# Build a single-file, self-contained `engram` binary for THIS platform via
# PyInstaller, into bin/<os>_<arch>/engram. Run once per OS/arch you support
# (macOS arm64/x86, Linux x86, …) — ideally in CI. Default (text recall) only;
# the semantic extra is too heavy to bundle and stays an opt-in uv install.
set -euo pipefail
cd "$(dirname "$0")/.."

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
# Output root defaults to the committed bin/ (handy for local dev). CI overrides
# it with a CLEAN staging dir (ENGRAM_BIN_DIR=stage) so the uploaded artifact
# holds ONLY this runner's freshly-built arch — never the other platform's stale
# binary carried in from the git checkout. That stale copy is what let a
# last-writer-wins race in the commit job resurrect old binaries.
OUT="${ENGRAM_BIN_DIR:-bin}/${OS}_${ARCH}"

echo "Building engram binary for ${OS}_${ARCH}…"
uv sync --extra build >/dev/null
uv run pyinstaller --onefile --clean --noconfirm --name engram \
  --paths src \
  --collect-submodules engram \
  --collect-submodules mcp.server \
  --collect-submodules mcp.shared \
  --collect-data mcp \
  --collect-all pydantic \
  --collect-all pydantic_core \
  --collect-all pydantic_settings \
  --collect-all ruamel.yaml \
  --collect-all anyio \
  --exclude-module mcp.cli \
  --exclude-module typer \
  --exclude-module fastembed \
  --exclude-module onnxruntime \
  --exclude-module numpy \
  --exclude-module tokenizers \
  scripts/_entry.py

mkdir -p "$OUT"
mv -f dist/engram "$OUT/engram"
chmod +x "$OUT/engram"
echo "✓ built $OUT/engram"
"$OUT/engram" --help 2>&1 | head -2 || true
