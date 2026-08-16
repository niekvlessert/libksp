#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rm -rf build-test
cmake -S . -B build-test -G Ninja -DCMAKE_BUILD_TYPE=Debug \
  -DTINYKSP_LIBVGM_SOURCE_DIR="$ROOT/libvgm-master" \
  -DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  -DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined'
cmake --build build-test --parallel 4
python3 tests/make_fixture.py build-test/parser.ksp
python3 tests/make_vm_fixture.py build-test/single.ksp
python3 tests/make_vm_fixture.py build-test/plus.ksp --plus
python3 tests/make_vm_fixture.py build-test/dual.ksp --dual
python3 tests/make_vm_fixture.py build-test/y8950.ksp --y8950
python3 tests/make_yamaha_vm_fixture.py build-test/fmpac.ksp
python3 tests/make_yamaha_vm_fixture.py build-test/opl4.ksp --opl4
python3 tests/make_vm_fixture.py build-test/adaptive.ksp --adaptive
python3 tests/make_vm_fixture.py build-test/adaptive-multitrack.ksp --adaptive-multitrack
python3 tests/make_kss_compare_fixture.py build-test/compare.ksp build-test/compare.kss
python3 tests/make_kss_compare_fixture.py build-test/compare-bad.ksp build-test/compare-bad.kss --bad
python3 tests/make_ksp103_fixture.py build-test/ksp103-valid.ksp
python3 tests/make_ksp103_fixture.py build-test/ksp103-equal.ksp --hvr-case equal-rank
python3 tests/make_ksp103_fixture.py build-test/ksp103-noeligible.ksp --no-eligible
python3 tests/make_ksp103_fixture.py build-test/ksp103-high.ksp --high-index
python3 tests/make_ksp103_fixture.py build-test/ksp103-warning.ksp --meta-case track-count-warning
python3 tests/make_ksp103_fixture.py build-test/ksp103-nometa.ksp --no-meta
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/runtime_smoke build-test/parser.ksp
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/z80_smoke
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/kss_vm_smoke
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/yamaha_smoke
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/vm_smoke build-test/single.ksp build-test/plus.ksp build-test/dual.ksp build-test/y8950.ksp build-test/adaptive.ksp
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/yamaha_vm_smoke build-test/fmpac.ksp build-test/opl4.ksp
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/ksp103_smoke \
  build-test/ksp103-valid.ksp build-test/ksp103-equal.ksp build-test/ksp103-noeligible.ksp \
  build-test/ksp103-high.ksp build-test/ksp103-warning.ksp build-test/ksp103-nometa.ksp
python3 tests/make_ksp103_fixture.py build-test/ksp104-valid.ksp --minor 4
python3 tests/make_ksp103_fixture.py build-test/ksp104-localized.ksp --minor 4 --meta-case localized
python3 tests/make_ksp103_fixture.py build-test/ksp104-nometa.ksp --minor 4 --no-meta
python3 tests/make_ksp103_fixture.py build-test/ksp105-valid.ksp --minor 5
python3 tests/make_ksp103_fixture.py build-test/ksp105-localized.ksp --minor 5 --meta-case localized
python3 tests/make_ksp103_fixture.py build-test/ksp105-nometa.ksp --minor 5 --no-meta
python3 tests/make_ksp105_fixture.py build-test/ksp105-shared.ksp --case valid-shared
python3 tests/make_ksp105_fixture.py build-test/ksp105-nonmonotonic.ksp --case valid-nonmonotonic
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/ksp104_smoke \
  build-test/ksp104-valid.ksp build-test/ksp104-localized.ksp \
  build-test/ksp104-nometa.ksp build-test/ksp103-valid.ksp
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/ksp105_smoke \
  build-test/ksp105-shared.ksp build-test/ksp105-nonmonotonic.ksp
for case in invalid-utf8 duplicate missing-equals nul bom crlf missing-version bad-sha bad-track-count; do
  python3 tests/make_ksp103_fixture.py "build-test/meta103-$case.ksp" --minor 3 --meta-case "$case"
  if ./build-test/tinyksp "build-test/meta103-$case.ksp" --list >/dev/null 2>&1; then
    echo "Malformed KSP 1.03 META unexpectedly accepted: $case" >&2
    exit 1
  fi
done
python3 tests/make_ksp103_fixture.py build-test/meta103-localized-invalid.ksp --minor 3 --meta-case localized
if ./build-test/tinyksp build-test/meta103-localized-invalid.ksp --list >/dev/null 2>&1; then
  echo "KSP 1.03 localized dotted key unexpectedly accepted" >&2
  exit 1
fi
for case in invalid-utf8 duplicate missing-equals nul bom crlf missing-version bad-sha bad-track-count duplicate-localized bad-localized-empty bad-localized-case bad-localized-dot bad-localized-hyphen bad-localized-primary bad-localized-long bad-default-language metadata-version-1; do
  python3 tests/make_ksp103_fixture.py "build-test/meta104-$case.ksp" --minor 4 --meta-case "$case"
  if ./build-test/tinyksp "build-test/meta104-$case.ksp" --list >/dev/null 2>&1; then
    echo "Malformed KSP 1.04 META unexpectedly accepted: $case" >&2
    exit 1
  fi
done
python3 tests/make_ksp103_fixture.py build-test/meta103-version2-invalid.ksp --minor 3 --meta-case metadata-version-2
if ./build-test/tinyksp build-test/meta103-version2-invalid.ksp --list >/dev/null 2>&1; then
  echo "KSP 1.03 metadata_version=2 unexpectedly accepted" >&2
  exit 1
fi
for case in bad-fallback overlap bad-magic; do
  python3 tests/make_ksp103_fixture.py "build-test/hvr-$case.ksp" --hvr-case "$case"
  if ./build-test/tinyksp "build-test/hvr-$case.ksp" --list >/dev/null 2>&1; then
    echo "Malformed HVR1 unexpectedly accepted: $case" >&2
    exit 1
  fi
done
for case in invalid-partial invalid-mismatch invalid-streamable-backward invalid-control-leaf; do
  python3 tests/make_ksp105_fixture.py "build-test/ksp105-$case.ksp" --case "$case"
  if ./build-test/tinyksp "build-test/ksp105-$case.ksp" --list >/dev/null 2>&1; then
    echo "Malformed KSP 1.05 shared payload unexpectedly accepted: $case" >&2
    exit 1
  fi
done
python3 tests/make_ksp103_fixture.py build-test/meta105-version1-invalid.ksp --minor 5 --meta-case metadata-version-1
if ./build-test/tinyksp build-test/meta105-version1-invalid.ksp --list >/dev/null 2>&1; then
  echo "KSP 1.05 metadata_version=1 unexpectedly accepted" >&2
  exit 1
fi
for minor in 0 1 2 3 4 5; do
  python3 tests/make_ksp103_fixture.py "build-test/minor$minor.ksp" --minor "$minor"
  ./build-test/tinyksp "build-test/minor$minor.ksp" --list >/dev/null
done
echo 'KSP 1.00-1.05 and malformed META/HVR1/shared-view validation passed'

python3 tools/upgrade_meta_103_to_104.py build-test/meta103-localized-invalid.ksp build-test/meta103-localized-upgraded.ksp >/dev/null
./build-test/tinyksp build-test/meta103-localized-upgraded.ksp --list | grep -q 'KSP version: 1.04'
./build-test/tinyksp build-test/meta103-localized-upgraded.ksp --list | grep -q 'metadata_version: 2'
./build-test/tinyksp build-test/meta103-localized-upgraded.ksp --list | grep -q 'title.ja: パロディウスだ!'
echo 'KSP 1.03 localized META upgrade tool validation passed'

ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ./build-test/tinyksp build-test/y8950.ksp --track 1 --seconds 1 --wav build-test/test.wav
python3 - <<'PY'
import wave
with wave.open('build-test/test.wav','rb') as w:
    assert (w.getnchannels(),w.getframerate(),w.getsampwidth(),w.getnframes()) == (2,44100,2,44100)
print('WAV validation passed')
PY

./build-test/tinyksp -v | grep -qx 'TinyKSP standalone VM 1.9.9'
./build-test/tinyksp --version | grep -qx 'TinyKSP standalone VM 1.9.9'
./build-test/tinyksp build-test/compare.kss --track 1 --dry-run | grep -q 'KSS information'
./build-test/tinyksp --compare build-test/compare.ksp build-test/compare.kss --track 1 --seconds 1 | grep -q 'Result: IDENTICAL'
set +e
./build-test/tinyksp --compare build-test/compare-bad.ksp build-test/compare-bad.kss --track 1 --seconds 1 > build-test/compare-bad.txt
compare_rc=$?
set -e
[ "$compare_rc" -eq 3 ]
grep -q 'Result: DIFFERENT' build-test/compare-bad.txt
grep -q 'INIT | PSG' build-test/compare-bad.txt
echo 'KSS direct playback and KSP/KSS comparator validation passed'
./build-test/tinyksp build-test/adaptive.ksp --list | grep -q 'type 1: Dual SCC + PSG'
./build-test/tinyksp build-test/parser.ksp --list | grep -q 'custom.field: custom value'
./build-test/tinyksp build-test/parser.ksp --list | grep -q 'KSP version: 1.02'
./build-test/tinyksp build-test/adaptive.ksp --track 1 --variant 1 --dry-run | grep -q 'channels=13'
./build-test/tinyksp build-test/ksp103-valid.ksp --list | grep -q 'KSP version: 1.03'
./build-test/tinyksp build-test/ksp103-valid.ksp --list | grep -q 'type 1: Dual SCC + PSG (rank 300)'
./build-test/tinyksp build-test/ksp103-valid.ksp --list | grep -q 'metadata_version: 1'
./build-test/tinyksp build-test/ksp104-localized.ksp --list | grep -q 'title.ja: パロディウスだ!'
./build-test/tinyksp build-test/ksp104-localized.ksp --list | grep -q 'title.pt-br: Parodius Da!'
./build-test/tinyksp build-test/ksp104-localized.ksp --list | grep -q 'title.zh-hant:'
./build-test/tinyksp build-test/ksp104-localized.ksp --list | grep -q 'future_label.ja:'
./build-test/tinyksp build-test/ksp104-localized.ksp --list | grep -q 'default_language: en'
./build-test/tinyksp build-test/ksp104-localized.ksp --list | grep -q 'KSP version: 1.04'
./build-test/tinyksp build-test/ksp105-localized.ksp --list | grep -q 'KSP version: 1.05'
./build-test/tinyksp build-test/ksp105-localized.ksp --list | grep -q 'metadata_version: 2'
./build-test/tinyksp build-test/ksp105-localized.ksp --list | grep -q 'title.ja:' 
./build-test/tinyksp build-test/fmpac.ksp --track 1 --dry-run | grep -q 'FM-PAC writes='
./build-test/tinyksp build-test/opl4.ksp --track 1 --dry-run | grep -q 'MWK samples=1'
echo 'CLI variant listing/selection and Yamaha-device validation passed' 
python3 tests/live_controls_smoke.py build-test/tinyksp build-test/adaptive-multitrack.ksp
python3 tests/playlist_smoke.py build-test/tinyksp build-test/adaptive-multitrack.ksp
python3 tests/manual_next_file_smoke.py build-test/tinyksp build-test/adaptive-multitrack.ksp

rm -rf build-clang-test
CC=clang CXX=clang++ cmake -S . -B build-clang-test -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DTINYKSP_LIBVGM_SOURCE_DIR="$ROOT/libvgm-master"
cmake --build build-clang-test --parallel 4
./build-clang-test/tinyksp build-test/parser.ksp --list | grep -q 'General META fields'
./build-clang-test/ksp103_smoke build-test/ksp103-valid.ksp build-test/ksp103-equal.ksp build-test/ksp103-noeligible.ksp build-test/ksp103-high.ksp build-test/ksp103-warning.ksp build-test/ksp103-nometa.ksp
./build-clang-test/ksp104_smoke build-test/ksp104-valid.ksp build-test/ksp104-localized.ksp build-test/ksp104-nometa.ksp build-test/ksp103-valid.ksp
./build-clang-test/ksp105_smoke build-test/ksp105-shared.ksp build-test/ksp105-nonmonotonic.ksp
echo 'Clang/macOS-compatible build validation passed'

clang++ -std=c++17 -DTINYKSP_TEST_WINDOWS -Itests/windows_stubs -Isrc \
  -fsyntax-only src/standalone_player.cpp
echo 'Windows console/audio frontend syntax validation passed'
