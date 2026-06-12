#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" "$SCRIPT_DIR/descargar_partidos.py" "$@"
