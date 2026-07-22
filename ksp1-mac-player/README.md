# KSP 1.01 Mac Player

A clean KSP 1.00/1.01 implementation built around the current SDL2/libkss playback architecture from `src/kspplayer.c` in `niekvlessert/libkss_conversion_tools`.

This directory intentionally starts fresh:

- no KSSX/KCPX/KCPZ parser;
- no game-specific detection;
- no 8-bit track/page limitation;
- one standalone KSP 1.00/1.01 parser and page materializer;
- one SDL/libkss command-line player;
- the complete current KSP 1.01 specification;
- byte-validation tests and sample packs.

## Included

```text
src/ksp1_runtime.c/.h  KSP 1.00/1.01 parser and materializer
src/ksp1_desktop_bridge.c/.h  dynamic-page and dual-SCC ABI bridge
src/ksp1_channel_control.c/.h  SCC key mapping, mute masks, status formatting
src/zx0.c/.h          bounded forward ZX0 decoder
src/ksp1player.c      SDL2/libkss player
src/ksp1tool.c        info, validation and extraction utility
spec/                  authoritative KSP 1.01 specification
samples/               parser fixtures plus dual-SCC regression packs
scripts/               macOS bootstrap and test scripts
tests/                 page-materialization smoke tests
```

## Implemented KSP 1.01 features

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
- dynamic page-switch gateway: 8-bit A compatibility for up to 256 pages, 16-bit HL above 256 pages
- two independently clocked SCC instances on desktop
- live elapsed/total playback clock based on rendered audio frames
- per-channel SCC muting: keys `1`-`5` for SCC A and `6`-`0` for SCC B
- KSP1 dual-SCC callbacks at `D900/D904/D908`
- compatibility translation for early `D900/D903` dual-SCC packs
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
- Up arrow or `]`: seek forward 10 seconds
- Down arrow or `[`: seek backward 10 seconds
- `}`: seek forward 60 seconds
- `{`: seek backward 60 seconds
- `1`-`5`: toggle channels 1-5 on SCC A
- `6`, `7`, `8`, `9`, `0`: toggle channels 1-5 on SCC B
- Escape, `q`, or Ctrl-C: quit

The live status line shows `MM:SS / MM:SS`. Enabled channels retain their key
number; muted channels are shown as `-`, for example:

```text
00:12 / 03:10  SCC A [1 2 - 4 5]  SCC B [6 7 8 - 0]
```

Muting does not stop register processing. Re-enabling a channel resumes it at
its current waveform, frequency, phase, and volume state.

Seeking is implemented by resetting the selected track and rendering discarded
audio from INIT up to the requested timestamp. This reconstructs Z80 memory,
dynamic KSP pages, both SCC cartridges, waveform state, loop detection, and
audio filters instead of attempting an unsafe memory or song-pointer jump.
Long forward seeks can therefore take a moment on dual-SCC tracks.

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

The tests reconstruct and CRC-check every parser fixture. They also verify the exact
runtime callback code injected for the ESCHATOS native dual-SCC ABI and the older
Megami Tensei II `D900/D903` ABI. The ESCHATOS regression also verifies its
A-only page request gateway, preventing the former bogus HL request `0x67CD`.
Channel-control tests verify the `1`-`0` key mapping, five-bit SCC mute masks,
and status-line rendering.

## Current limitations

- Embedded MWK upload and OPL4/YRW801 hookup are defined by the format but are not yet connected to the clean player. PSG, single SCC, dual SCC and the Y8950/YM2413 KSCC flags are bridged to libkss.
- BNK8/BN16 resources are parsed as resources, but engines that require a live mapper-bank callback need a dedicated libkss mapper bridge.
- Dynamic page materialization currently happens in the libkss memory-write callback. This is functionally direct but should later be moved to a lock-free request queue for hard real-time audio safety.
- macOS audio could not be heard in the Linux build environment used to assemble this package. Parser, callback injection, strict C compilation and every included page were tested; the bootstrap builds against the current upstream libkss on the Mac.

## Format authority

`spec/KSP_FORMAT_SPEC_1.01.md` is the authoritative specification copied into this project. The player accepts KSP 1.00 and 1.01 and does not depend on the older KCP formats.
