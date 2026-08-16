# TinyKSP 1.9.4 test report

## Custom MWK 12/16-bit length correction

- MWK payload lengths remain byte counts for file parsing and RAM placement.
- OPL4 voice lengths now use the decoded sample count from each wave header.
- Added an exact custom 12-bit MWK regression: 256 decoded samples occupy 384
  payload bytes and must loop at sample 256, not continue into zero-filled RAM.
- Release `z80_smoke` and `yamaha_smoke` pass.
- Address/undefined-sanitizer parser, Z80, VM, Yamaha and KSP conformance smoke
  tests reached the extended malformed-input phase without a detected sanitizer
  failure; that long batch was stopped by the execution time limit.

## Dawn of Sorrow v1.11 validation

- Track 1 rendered for 35 seconds at 44.1 kHz stereo.
- Exactly 2,100 engine PLAY calls were executed at 60 Hz.
- 17 custom MWK samples loaded, including the two new 12-bit chord waves.
- All 29 tracks completed two-second smoke renders with exactly 120 PLAY calls
  each.

## Historical TinyKSP 1.9.3 report

## TinyKSP 1.9.3 pitch correction

- Exact YMF278B normal-pitch regression: `FNUM=0, OCTAVE=1` replays a 32-sample waveform at the expected period.
- OPL4 PCM sample duration is no longer halved by a doubled playback step.

## Corrected defects retained from 1.9.2

1. YMF278B format `01` was decoded as 16-bit instead of 12-bit.
2. Format `10` was decoded as 12-bit instead of 16-bit.
3. The 12-bit three-byte packing used the wrong byte/nibble order.
4. MWK custom wave headers were also aliased over YRW801 ROM waves `0..63`.
5. The declared KSP `PAGE3_WORKRAM` profile was not initialized to `FFh`.

## Exact regression coverage

- Synthetic YRW801 ROM tests exercise smooth 12-bit and 16-bit PCM waves.
- The old format mapping or old 12-bit nibble order fails the smoothness check.
- Custom MWK playback is addressed at RAM wave 384 and no longer relies on a
  ROM-wave alias.
- Register `20h+n` still resolves wave `134h` and F-number `2D5h` for the exact
  regression write sequence.
- Release CTest: `z80_smoke` and `yamaha_smoke` pass.
- Address/undefined-sanitizer parser, Z80, VM, Yamaha VM and KSP 1.03 tests pass.

## Dawn of Sorrow tracks 1-5

Pack: `Castlevania_Dawn_of_Sorrow_MoonSound_KSP1_1.04_OneDisk_v1.1.ksp` with
external `yrw801.rom`.

All five tracks completed five-second 44.1 kHz renders with exactly 300 PLAY
calls. Spectral flatness in the first five seconds changed as follows:

| Track | 1.9.1 | 1.9.2 |
|---:|---:|---:|
| 1 | 0.1911 | 0.0152 |
| 2 | 0.5184 | 0.0035 |
| 3 | 0.3528 | 0.0007 |
| 4 | 0.0180 | 0.0180 |
| 5 | 0.3804 | 0.0039 |

The large reduction on tracks 1, 2, 3 and 5 is consistent with removal of the
noise-like 12-bit decoding. Track 4 is bit-identical for the first five seconds
because that section uses only 8-bit custom RAM samples.

## Track 4 timing investigation

- TinyKSP performs exactly 60 PLAY calls per second.
- The track declares tempo 138 and the engine converts SSEQ ticks using the
  correct `tempo / 75` ticks-per-frame accumulator.
- The observed stream uses only implemented commands: notes, rests, track-open,
  call, jump, pan, volume, note-wait, tempo, return and end.
- No nested calls overwrite the engine's one-level per-track return slot.
- No skipped PLAY calls or unsupported-command termination was found.

Therefore the remaining audible timing problem is not caused by TinyKSP's host
scheduler. A byte-level comparison with the original SSEQ and the converter
source is required to locate it in the compact DSQ data or Z80 SSEQ interpreter.
