#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor/libkss_conversion_tools"
BUILD="$ROOT/build"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "warning: this bootstrap script is intended for macOS" >&2
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required for CMake and SDL2: https://brew.sh" >&2
  exit 1
fi

missing=()
command -v cmake >/dev/null 2>&1 || missing+=(cmake)
command -v pkg-config >/dev/null 2>&1 || missing+=(pkg-config)
brew list --versions sdl2 >/dev/null 2>&1 || missing+=(sdl2)
if ((${#missing[@]})); then
  echo "Installing: ${missing[*]}"
  brew install "${missing[@]}"
fi

if [[ ! -d "$VENDOR/.git" ]]; then
  mkdir -p "$(dirname "$VENDOR")"
  git clone --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/niekvlessert/libkss_conversion_tools.git "$VENDOR"
else
  git -C "$VENDOR" pull --ff-only
  git -C "$VENDOR" submodule update --init --recursive
fi

cmake -S "$ROOT" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DKSP1_BUILD_AUDIO_PLAYER=ON
cmake --build "$BUILD" --parallel

echo
echo "Built:"
echo "  $BUILD/ksp1player"
echo "  $BUILD/ksp1tool"
echo
echo "Try:"
echo "  $BUILD/ksp1player --info $ROOT/samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp"
echo "  $BUILD/ksp1player -s 0 $ROOT/samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp"
