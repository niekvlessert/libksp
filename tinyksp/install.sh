#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
LOG="$PWD/tinyksp-build.log"
exec > >(tee "$LOG") 2>&1
trap 'status=$?; echo; echo "Build failed (exit $status). Log: $LOG"; exit $status' ERR

echo "Installing TinyKSP 1.9.9 KSS/compare dependencies..."
pkg update -y
pkg install -y clang cmake ninja mpv python
if [ ! -d "$HOME/storage/downloads" ]; then
  echo; echo "Requesting Android shared-storage access..."
  termux-setup-storage || true
fi

echo; echo "Building direct KSP/KSS Z80 and sound-device runtime (no libkss player layer)..."
rm -rf build-termux
cmake -S . -B build-termux -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" -DTINYKSP_LIBVGM_SOURCE_DIR="$PWD/libvgm-master"
cmake --build build-termux --parallel 2
rm -f "$PREFIX/bin/tinyksp"
cmake --install build-termux
hash -r 2>/dev/null || true

echo; echo "Installed: $PREFIX/bin/tinyksp"
"$PREFIX/bin/tinyksp" -v
echo "Run: hash -r && tinyksp"
echo "KSS: tinyksp file.kss --track 1"
echo "Compare: tinyksp --compare file.ksp file.kss --track 1"
echo "Optional MoonSound ROM: copy yrw801.rom beside the KSP or use --yrw801 FILE"
echo "Log: $LOG"
