#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
swiftc "$ROOT/GentlrWidget.swift" -o "$ROOT/GentlrWidget"
