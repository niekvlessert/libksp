# Test report

Package date: 2026-07-21

## Executed in the build environment

- C99 GCC release build of `ksp1_runtime`, `ksp1tool`, and test executable
- `-Wall -Wextra -Wpedantic` clean build
- AddressSanitizer and UndefinedBehaviorSanitizer page tests
- API-compatible SDL/libkss stub compile and link of `ksp1player.c`
- `--info` through the clean player front end
- full page reconstruction and CRC validation
- KSCC bridge validation for first and last tracks

## Tested packages

```text
SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp
    1 engine, 43 pages, 43 tracks, encoding 4

XAK_GAZELL_KSP1_HYBRID_RAM_VRAM.ksp
    1 engine, 232 pages, 233 tracks, encoding 4

SOLIDSNK_KSP1_RESOURCE_MAP.ksp
    1 engine, 43 pages, 43 tracks, encoding 3
```

All reconstructed pages passed their stored CRCs.

## Not executable in this environment

The package was assembled in a Linux sandbox without SDL2/libkss checkout or a
macOS audio device. The included macOS bootstrap fetches the current upstream
repository and compiles against its patched libkss. Actual audible playback on
macOS therefore remains the final machine test.
