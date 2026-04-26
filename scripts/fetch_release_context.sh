#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PY_SCRIPT="${SCRIPT_DIR}/fetch_release_context.py"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[fetch_release_context.sh][error] python3 is required but was not found in PATH." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$PY_SCRIPT" "$@"
