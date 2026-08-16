#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORK=${TMPDIR:-/tmp}/ksp_analyse_z80dasm_build_$$
trap 'rm -rf "$WORK"' EXIT INT TERM
mkdir -p "$WORK"
tar -xzf "$HERE/third_party/z80dasm_1.1.6.orig.tar.gz" -C "$WORK"
SRC=$(find "$WORK" -maxdepth 1 -type d -name 'z80dasm-*' | head -1)
[ -n "$SRC" ] || { echo "z80dasm source directory not found" >&2; exit 1; }
cd "$SRC"
./configure
make
cp src/z80dasm "$HERE/z80dasm"
chmod +x "$HERE/z80dasm"
echo "Built: $HERE/z80dasm"
