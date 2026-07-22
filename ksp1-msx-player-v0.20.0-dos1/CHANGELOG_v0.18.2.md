# KSP1PLAY 0.18.2

- Added explicit FMPAC/YM2413 key-off before every disk-backed `read_at` and streamed ZX0 seek path.
- Disables rhythm mode and keys off all nine melodic channels before DOS pauses playback.
- Leaves instrument and volume registers untouched so live dynamic-page playback can resume naturally.
- Reuses one timing-safe YM2413 register writer for both disk mute and full hardware reset.
- VRAM-cached reads remain unchanged and do not mute FMPAC.
- Retains all v0.18.1 KSP 1.01, Screen 5, HPOL, dual-SCC, MoonSound and disk-loading functionality.
