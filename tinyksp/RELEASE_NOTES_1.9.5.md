# TinyKSP 1.9.5

## MoonSound backend

- Replaced TinyKSP's custom YMF278B wave/PCM renderer with libvgm's
  openMSX-derived 24-slot YMF278B implementation.
- Kept TinyKSP's existing OPL3/FM renderer for the MoonSound FM half, avoiding
  duplicate FM output.
- Mirrored FM control writes into the libvgm device so the NEW2/OPL4 enable
  state follows the engine's actual port writes.
- Routed YRW801 ROM, 2 MiB MoonSound RAM, MWK wave headers and sample payloads,
  wave-register reads/writes, envelopes, interpolation, looping, panning, LFO,
  damping, pseudo-reverb and 24-channel mute state through libvgm.
- Preserved the 1.9.2-1.9.4 MWK format, pitch and 12-bit/16-bit length fixes.

## Build

- CMake fetches `ValleyBell/libvgm` automatically.
- Offline builds can set `TINYKSP_LIBVGM_SOURCE_DIR` to a local libvgm checkout.
- `yrw801.rom` remains external and is not included.
