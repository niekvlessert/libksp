# KSP 1.0 Mac Player

A clean KSP 1.0 implementation built around the current SDL2/libkss playback architecture from `src/kspplayer.c` in `niekvlessert/libkss_conversion_tools`.

This directory intentionally starts fresh:

- no KSSX/KCPX/KCPZ parser;
- no game-specific detection;
- no 8-bit track/page limitation;
- one standalone KSP 1.0 parser and page materializer;
- one SDL/libkss command-line player;
- the complete current KSP 1.0 specification;
- byte-validation tests and sample packs.

## Included

```text
src/ksp1_runtime.c/.h  KSP 1.0 parser and materializer
src/zx0.c/.h          bounded forward ZX0 decoder
src/ksp1player.c      SDL2/libkss player
src/ksp1tool.c        info, validation and extraction utility
spec/                  authoritative KSP 1.0 specification
samples/               Solid Snake and Xak Gazell hybrid packs
scripts/               macOS bootstrap and test scripts
tests/                 page-materialization smoke tests
```

## Implemented KSP 1.0 features

- 16-bit engine, page, track and resource indices
- header and index CRC validation
- UTF-8 string table
- engine templates using NONE or ZX0
- page encoding 0: sparse overlay
- page encoding 1: complete page
- page encoding 2: `PBM1` plus slabbed `PBLK/PBK1`
- page encoding 3: `RMP1` resource-range reconstruction
- page encoding 4: `HPOL/HPL1` hybrid RAM/VRAM/cold pool
- resource compression NONE, ZX0 and `KZB1` block streams
- per-page CRC validation
- dynamic 16-bit page-switch gateway
- public track navigation above track 255
- hidden-track skipping
- KSCC bridge generation for libkss

The desktop implementation materializes resources in host memory. RAM/VRAM/cold tiers are still parsed exactly as specified, but are storage and future-MSX placement hints on macOS.

## Build on macOS

From this directory:

```bash
./scripts/bootstrap-macos.sh
```

The script installs missing Homebrew `cmake`/`sdl2` packages, clones the current conversion-tools repository recursively into `vendor/`, and builds only its bundled libkss dependency plus this clean player.

Manual equivalent:

```bash
brew install cmake sdl2
git clone --depth 1 --recurse-submodules --shallow-submodules \
  https://github.com/niekvlessert/libkss_conversion_tools.git \
  vendor/libkss_conversion_tools
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

## Use

Show all engines and tracks:

```bash
./build/ksp1player --info samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp
```

Validate every reconstructed page:

```bash
./build/ksp1player --validate samples/XAK_GAZELL_KSP1_HYBRID_RAM_VRAM.ksp
```

Play track 6:

```bash
./build/ksp1player --song 6 samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp
```

During playback:

- Left arrow: previous visible track
- Right arrow: next visible track
- Escape, `q`, or Ctrl-C: quit

Useful options:

```text
--seconds 0     use track duration metadata
--seconds 180   force three minutes
--fade 5        five-second fade
--loops 1       fade after the first detected loop
--rate 48000
--channels 2
```

## Utility

`ksp1tool` does not require SDL or libkss:

```bash
./build/ksp1tool --validate file.ksp
./build/ksp1tool --info file.ksp
./build/ksp1tool --song 0 --output track0.kss file.ksp
./build/ksp1tool --page 0 --output page0.bin file.ksp
```

## Tests

```bash
./scripts/test.sh
```

The tests reconstruct and CRC-check every page in the included Solid Snake and Gazell packages.

## Current limitations

- Embedded MWK upload and OPL4/YRW801 hookup are defined by the format but are not yet connected to the clean player. PSG, SCC and the Y8950/YM2413 KSCC flags are bridged to libkss.
- BNK8/BN16 resources are parsed as resources, but engines that require a live mapper-bank callback need a dedicated libkss mapper bridge.
- Dynamic page materialization currently happens in the libkss memory-write callback. This is functionally direct but should later be moved to a lock-free request queue for hard real-time audio safety.
- macOS audio could not be heard in the Linux build environment used to assemble this package. The parser and every included page were tested byte-for-byte; the bootstrap builds against the current upstream libkss on the Mac.

## Format authority

`spec/KSP_FORMAT_SPEC_1.0.md` is the authoritative specification copied into this project. The player does not depend on the older KCP formats.
