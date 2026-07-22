# Test report

Package date: 2026-07-21
Version: 1.0.4

## Executed in the build environment

- C99 GCC release build of `ksp1_runtime`, `ksp1tool`, and all tests
- `-Wall -Wextra -Wpedantic` clean runtime build
- strict `-Werror` API-compatible SDL/libkss/emu2212 syntax compile of `ksp1player.c`
- AddressSanitizer and UndefinedBehaviorSanitizer pass for all seven tests
- full page reconstruction and stored CRC validation
- exact dual-SCC ABI detection and injected callback-byte regression tests
- ESCHATOS A-only page gateway regression (`A=1`, stale `HL=$67CD`)
- SCC key mapping, mute-mask toggling, and display formatting regression tests
- seek key mapping and start/end clamping regression tests

## Tested packages

```text
SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp
    1 engine, 43 pages, 43 tracks, encoding 4

XAK_GAZELL_KSP1_HYBRID_RAM_VRAM.ksp
    1 engine, 232 pages, 233 tracks, encoding 4

SOLIDSNK_KSP1_RESOURCE_MAP.ksp
    1 engine, 43 pages, 43 tracks, encoding 3

ESCHATOS_N163_Dual_SCC_KSP1_1.0.ksp
    1 engine, 124 pages, 13 tracks
    native KSP1 D900/D904/D908 dual-SCC bridge verified
    8-bit A page gateway verified; bogus HL page 26573 is no longer used

Megami_Tensei_II_Dual_SCC_KSP1_1.0.ksp
    1 engine, 122 pages, 77 tracks
    legacy D900 page / D903 SCC selector translation verified
```

All seven CTest cases passed in release and ASan/UBSan builds. Both included
dual-SCC packages passed complete page reconstruction and CRC validation. ABI
detection and callback injection were checked for all 13 ESCHATOS tracks and
all 77 Megami Tensei II tracks.

## Seeking

- `[` and Down map to -10 seconds; `]` and Up map to +10 seconds
- `{` maps to -60 seconds; `}` maps to +60 seconds
- targets clamp to frame zero and the configured end frame
- playback uses a reset-and-render reconstruction path rather than pointer jumps
- current SCC channel masks are reapplied after reset
- both dual-SCC ABIs remain active during discarded rendering

## Not executable in this environment

The package was assembled in a Linux sandbox without a macOS audio device or
the fetched upstream dependency tree. The macOS bootstrap fetches the current
conversion-tools repository and builds the complete SDL/libkss player. Audible
playback and interactive keyboard behavior remain the final Mac test.
