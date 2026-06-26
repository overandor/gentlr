#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
"$ROOT/bootstrap.sh"
"$ROOT/build-ui.sh"
echo "Installed gentlr."
echo "Run UI: $ROOT/gentlr-ui"
echo "Run dry ML check: $ROOT/gentlr-dry"
