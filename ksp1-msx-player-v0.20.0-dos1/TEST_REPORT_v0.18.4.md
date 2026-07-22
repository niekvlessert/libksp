# KSP1PLAY 0.18.4 test report

Build result:

- COM size: 16,033 bytes
- SHA-256: `6d10c4bb00f0cb9f0cf25478f142052ac59f77998a59d1fcc5dee63c6ec15fe2`
- Resident core end: `1B6Fh`
- Dynamic/dual-SCC gateway end: `2143h`
- Screen 5 UI end: `34B8h`
- HPOL caches remain fixed at `3500h` and `3700h`
- MoonSound module end: `3FA1h`

Passed model and package regressions:

- sparse-overlay and HPOL page reconstruction
- streamed ZX0 refill model
- dynamic-page and dual-SCC relocation model
- KSP 1.01 PAGE2_RUNTIME/PAGE3_WORKRAM model
- FMPAC disk-I/O key-off model
- track-selector pagination/title/cache model using all 24 titled Nemesis 3 tracks
- Screen 5 UI/HPOL fixed-layout validation
- explicit regression that the VRAM clear loop reloads zero before every output byte
- compact 64-column font/layout markers and player-cache rendering path

The exact v0.18.3 corruption was identified in `ui_clear_vram_loop`: only the first byte was zero; subsequent bytes used `B OR C` from the loop counter. Version 0.18.4 executes `XOR A` immediately before every VRAM output.

Runtime limitation: this environment does not contain openMSX, so final visual presentation and physical keyboard timing still require emulator or real-MSX validation.
