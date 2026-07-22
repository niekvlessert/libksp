# KSP1PLAY 0.18.7 test report

## Change under test

The common Screen 5 text renderer now treats every byte below `20h` as an
end-of-line condition. CR (`0Dh`), LF (`0Ah`) and any other control byte can no
longer reach the fallback `?` glyph path, regardless of whether the string came
from a package name, track cache, metadata heading or active-playback title.

## Results

- Assembly: passed
- COM size: 16,033 bytes
- COM SHA-256: `1b2b042f92a65a5fc085a9cc464338f07bb137f60b00539eb1e4d0337f087d1c`
- UI boundary: `34FAh`, below HPOL cache at `3500h`
- Core boundary: `1BFBh`, below descriptors at `1C00h`
- Control-byte renderer regression: passed
- Incremental package and live-track repaint regression: passed
- KSP 1.01 PAGE2/PAGE3 runtime regression: passed
- Sparse, HPOL, ZX0, dual-SCC, MoonSound and FMPAC disk-mute regressions: passed
- Test disks rebuilt successfully

A physical MSX or openMSX visual run is still needed to confirm presentation on
the target VDP.
