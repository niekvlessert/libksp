# KSP1PLAY 0.16 — MoonSound/OPL4

## Added

- Accepts KSP hardware bit 6 (`0x40`) for YMF278B/OPL4/MoonSound.
- Detects MoonSound before loading an OPL4 engine and reports a hardware error
  when the required device is absent.
- Performs a defensive OPL4 shutdown on track changes, errors and exit:
  FM timers/IRQs are disabled, both FM register arrays are keyed off, the wave
  mixer is muted, and all 24 PCM slots are attenuated and damped.
- Restores neutral OPL4 mixer values immediately before engine `INIT`.
- Resolves a track-specific `MWK ` resource, falling back to the engine-default
  MWK resource.
- Supports raw MWK revisions `0Ch` and `0Dh`, including custom wave headers and
  sample uploads to MoonSound RAM.
- Supports MWK resources stored as raw, whole-stream ZX0, or `KZB1` independently
  compressed ZX0 blocks. Each unpacked block must fit the 16 KiB scratch segment.
- Keeps the v0.13 automatic 50/60 Hz VDP selection and restoration.

## Compatibility retained

The existing KSP1 parser, HPOL/sparse/complete-page loaders, VRAM cache,
DOS2 mapper handling, split-engine profile and Parodius dynamic-page gateway
remain in place. The older page-3 player was used only as an implementation
reference; its runtime layout was not imported.

## Memory

- Resident low page-0 code ends before `1C00h`.
- Dynamic gateway remains below `2200h`.
- Map buffer is `2200h–38FFh`.
- Stack is `3900h–39EFh`.
- Permanent MoonSound helpers occupy `3A00h–3FF1h`.

## Validation status

The bundled build and all pre-existing profile, sparse, CRC, mapper, ZX0 and
disk-image regression checks pass. Runtime playback still requires validation
with openMSX plus MoonSound or physical MSX hardware.
