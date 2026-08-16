#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
rm -rf build-termux
cmake -S . -B build-termux -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DTINYKSP_LIBVGM_SOURCE_DIR="$PWD/libvgm-master"
cmake --build build-termux --parallel 2
cmake --install build-termux
