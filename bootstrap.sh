#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd /private/tmp
if command -v brew >/dev/null 2>&1; then
  brew list libomp >/dev/null 2>&1 || brew install libomp
else
  echo "Homebrew not found. Install libomp before using XGBoost: https://brew.sh"
fi
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
