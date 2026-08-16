#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DTINYKSP_LIBVGM_SOURCE_DIR="$PWD/libvgm-master"
cmake --build build --parallel 2
./build/tinyksp -v
