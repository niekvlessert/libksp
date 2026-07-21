#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${1:-$ROOT/build}"

cmake -S "$ROOT" -B "$BUILD" -DKSP1_BUILD_AUDIO_PLAYER=OFF
cmake --build "$BUILD" --parallel
ctest --test-dir "$BUILD" --output-on-failure
"$BUILD/ksp1tool" --validate "$ROOT/samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp"
"$BUILD/ksp1tool" --validate "$ROOT/samples/XAK_GAZELL_KSP1_HYBRID_RAM_VRAM.ksp"

"$BUILD/ksp1tool" --validate "$ROOT/samples/SOLIDSNK_KSP1_RESOURCE_MAP.ksp"
