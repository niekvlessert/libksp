# Building TinyKSP 1.9.9

TinyKSP is portable C++17/CMake. TinyKSP 1.9.9 uses the pinned `libvgm-master/`
and `libkss/` submodules for its sound cores. Initialize them, including
libkss's nested chip modules, after cloning:

```sh
git submodule update --init --recursive
```

If `libvgm-master/` is absent, CMake can still download libvgm automatically.
macOS live playback uses native Core Audio;
Termux and other non-macOS builds use `mpv`. Inspection, dry runs and WAV
rendering do not require a live-audio backend.

## Generic CMake build

The default build requires Git and network access for the initial libvgm fetch.

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
./build/tinyksp -v
```

## Linux

Use the generic build above. The resulting executable is `build/tinyksp`.

## macOS

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

A universal executable can be produced by configuring
`CMAKE_OSX_ARCHITECTURES="arm64;x86_64"` on a suitable macOS host.

The macOS executable sends stereo PCM directly to the default Core Audio output
device and does not require `mpv`.

## Windows

From an x64 Visual Studio Native Tools command prompt:

```bat
cmake -S . -B build -A x64
cmake --build build --config Release
```

Or use MinGW-w64 with Ninja. Put `mpv.exe` in `PATH` for live playback, or use
`--wav`.

## Termux

```sh
chmod +x install.sh
./install.sh
```

## KSP specifications

The source includes strict reader specifications for KSP 1.03, 1.04 and 1.05.
KSP 1.05 retains metadata grammar 2 and adds safe shared physical payload views,
including exact cross-resource KZB1 block aliases.

## KSP 1.04 metadata repair tool

```sh
python3 tools/upgrade_meta_103_to_104.py INPUT.ksp OUTPUT.ksp
```

This only supports an uncompressed META resource because it edits the existing
payload in place and recomputes CRCs without moving offsets.

## MoonSound ROM

The standard 2 MiB YRW801 image is optional. TinyKSP searches beside the KSP,
the current directory and normal Downloads locations. It can also be specified
with `--yrw801 FILE` or `TINYKSP_YRW801_ROM`.

## Tests

```sh
./tests/run_linux_tests.sh
```

The suite covers GCC/Clang, ASan/UBSan, Windows frontend syntax, KSP 1.00-1.05,
localized META, HVAR/HVR1, exact/invalid KSP 1.05 aliases, 29 MWK resources
sharing a physical KZB1 sample block, non-monotonic block order, Z80, Yamaha and
SCC devices, FM-PAC rhythm mode, KSS/KSSX direct-VM playback, WAV rendering,
seeking and live controls.


## Custom or offline dependency checkouts

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DTINYKSP_LIBVGM_SOURCE_DIR=/path/to/libvgm
cmake --build build --parallel
```

Set `TINYKSP_LIBKSS_SOURCE_DIR` similarly when using a separate libkss checkout.
