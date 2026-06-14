#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

MUNDIAL_PYTHONPATH="$SCRIPTS_DIR"
for dir in "$SCRIPTS_DIR"/[0-9][0-9]_*; do
  if [ -d "$dir" ]; then
    MUNDIAL_PYTHONPATH="$MUNDIAL_PYTHONPATH:$dir"
  fi
done
export PYTHONPATH="$MUNDIAL_PYTHONPATH${PYTHONPATH:+:$PYTHONPATH}"

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/00_orquestador/descargar_partidos.py" "$@"
