# KSP1PLAY 0.18.8 test report

## Change under test

The fixed-width Screen 5 renderer no longer places a NUL byte into the first
padding cell after copied text. The row is already prefilled with spaces, and
the glyph pass renders all 64 cells; previously that NUL was translated to the
fallback question-mark glyph.

## Results

- Assembly: passed
- COM size: 16,033 bytes
- COM SHA-256: `84da8ae0dac3d1ea620961d12092d22d84558271885b5772eb2aba401b4ab9c6`
- UI boundary: `34FBh`, below HPOL cache at `3500h`
- Core boundary: `1BFBh`, below descriptors at `1C00h`
- NUL-padding renderer regression: passed
- Control-byte renderer regression: passed
- Incremental package and live-track repaint regression: passed
- KSP 1.01 PAGE2/PAGE3 runtime regression: passed
- Sparse, HPOL, ZX0, dual-SCC, MoonSound and FMPAC disk-mute regressions: passed
- Test disks rebuilt successfully

A physical MSX or openMSX visual run is still needed for final presentation confirmation.
