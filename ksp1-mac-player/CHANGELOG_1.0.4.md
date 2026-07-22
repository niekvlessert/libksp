# Changelog 1.0.4

- Added safe timestamp seeking.
- Up/Down arrows and `[`/`]` seek by 10 seconds.
- `{`/`}` seek by 60 seconds.
- Seek targets clamp to the configured track duration.
- Seeking reconstructs state from INIT by rendering discarded audio, preserving
  dynamic pages, both SCC cartridges, waveforms, filter history, and channel masks.
- Loop-trigger fading is rebased after a seek; absolute duration fading remains.
- Added seek key/arithmetic regression tests.
- Retained all 1.0.3 dual-SCC and channel-control behavior.
