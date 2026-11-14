#!/usr/bin/env bash
# Atajo multiplataforma para la ingesta. En Windows usar Git Bash/WSL o
# directamente: python -m vacuinfo.cli ingestar
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python            # Linux / macOS
elif [[ -x .venv/Scripts/python.exe ]]; then
  PY=.venv/Scripts/python.exe    # Windows (Git Bash / MSYS)
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

exec "$PY" -m vacuinfo.cli ingestar "$@"
