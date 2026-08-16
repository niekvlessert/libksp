# TinyKSP 1.9.9 complete source package

This is the complete TinyKSP source tree with the libvgm YMF278B wave/PCM backend already integrated.

- CMake uses the pinned `libvgm-master` and `libkss` submodules during
  configuration. Pass `-DTINYKSP_LIBVGM_SOURCE_DIR=/path/to/libvgm` or
  `-DTINYKSP_LIBKSS_SOURCE_DIR=/path/to/libkss` to use another checkout.
- TinyKSP's existing OPL3/FM renderer remains active for the MoonSound FM half.
- macOS live playback uses the native Core Audio output; Termux continues to use mpv.
- YRW801 ROM, MoonSound RAM/MWK data, wave register I/O, envelopes, looping, panning and 24-slot PCM muting use libvgm.
- `yrw801.rom` is intentionally not bundled.
- Wildcard/multi-file KSP playlists and automatic next-track progression are implemented in the standalone frontend.
- Direct MSX KSS/KSSX playback and KSP-vs-KSS trace/PCM comparison are included in 1.9.9.

Build:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```
