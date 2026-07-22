# KSP1PLAY 0.18.3 test report

Build result:

- COM size: 16,033 bytes
- SHA-256: `78abbe0cc287a2defbc26d27deddc8163bd0e7bd2d51d18279cae90d140c1455`
- Resident core end: `1B6Fh`
- Dynamic/dual-SCC gateway end: `2143h`
- Screen 5 UI end: `34D4h`
- HPOL caches remain fixed at `3500h` and `3700h`
- MoonSound module end: `3FA1h`

Passed model and package regressions:

- sparse-overlay and HPOL page reconstruction
- streamed ZX0 refill model
- dynamic-page and dual-SCC relocation model
- Screen 5/HPOL memory-layout model
- KSP 1.01 PAGE2_RUNTIME/PAGE3_WORKRAM model
- FMPAC disk-I/O key-off model
- track-selector pagination/title/cache model using all 24 titled Nemesis 3 tracks

Runtime limitation: this environment does not contain openMSX, so the final visual presentation and physical keyboard timing still require an emulator or real-MSX test.
