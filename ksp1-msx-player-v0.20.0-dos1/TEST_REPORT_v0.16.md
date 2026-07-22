# KSP1PLAY 0.16 test report

## Build-time checks

- Bundled two-pass Z80 assembler completed successfully.
- Resident code remains below the fixed KSP descriptor area at `1C00h`.
- Dynamic callback remains below `2200h`.
- Page-0 map buffer ends at `3900h`.
- MoonSound helper module starts at `3A00h` and ends before `4000h`.
- Required automatic-refresh and MoonSound/MWK source markers are present.

## Existing regressions

- Solid Snake HPOL hybrid profile: passed.
- Solid Snake sparse-overlay profile and CRCs: passed.
- Nemesis 3 sparse-overlay profile and CRCs: passed.
- Xak Gazell unsupported-profile rejection: passed.
- ZX0 MSX model test: passed.
- Existing test disk image generation: passed.

## Result

`KSP1PLAY.COM` builds successfully. Runtime OPL4 playback was not executed in
this environment because openMSX and physical MoonSound hardware are unavailable.
