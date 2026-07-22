# KSP1PLAY 0.18.9 test report

## Change under test

Playback viewport calculation now uses the 13-row playback pane rather than the
15-row selector pane. With selected track 22 and old top index 8, the new top
index becomes 11 and the visible range is 11 through 23.

## Results

- Assembly: passed
- COM size: 16,033 bytes
- COM SHA-256: `8a96ec9538681c63229649344c49fe9c8d0a9ccceec9c7741b3ddfdc445859e6`
- Core boundary: `1BFBh`, below descriptors at `1C00h`
- UI boundary: `34FBh`, below HPOL cache at `3500h`
- Playback viewport model: passed; track 22 displays tracks 11..23
- Incremental package and live-track repaint regression: passed
- NUL-padding and control-character renderer regressions: passed
- KSP 1.01 PAGE2/PAGE3, sparse, HPOL, ZX0, dual-SCC, MoonSound and FMPAC disk-mute regressions: passed
- Test disks rebuilt successfully

A physical MSX or openMSX visual run remains necessary.
