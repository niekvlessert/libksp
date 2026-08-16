# Dawn of Sorrow KSP 1.04 — pitch and timing correction

Tested pack:
`Castlevania_Dawn_of_Sorrow_MoonSound_KSP1_1.04_OneDisk_v1.2_timingfix.ksp`

## TinyKSP 1.9.3 pitch defect

The YMF278B application manual defines `FNUM=0, OCTAVE=1` as normal 44.1 kHz
sample playback. TinyKSP 1.9.2 used octave 0 as normal. Consequently every
OPL4 PCM voice was one octave too high and one-shot percussion samples ended
in half their intended time.

TinyKSP 1.9.3 changes the playback step from `2^octave` to `2^(octave-1)` and
contains a waveform-period regression that detects the previous doubled rate.

## KSP engine timing defect

The Dawn compact SSEQ engine stored each decoded note/rest duration `N` directly
in a countdown which is decremented on later sequence ticks. The next command
was processed only on the tick after the counter reached zero, making every
wait last `N+1` ticks. Dense percussion accumulated much more delay than long
background notes and progressively moved out of sync.

Pack v1.2 corrects the engine itself: decoded nonzero waits are stored as `N-1`.
This is implemented in unused shared engine space and is not a game-specific
TinyKSP runtime workaround. The corrected KSP therefore also carries its timing
fix to native MSX players.

## Validation

- TinyKSP 1.9.3 `z80_smoke` and `yamaha_smoke`: pass.
- Track 1 corrected KSP register/key-on trace is identical to the isolated
  instruction-level wait-fix prototype across 8,400 video frames.
- All 29 tracks render for 10 seconds each with exactly 600 PLAY calls.
- All 29 tracks produce active OPL4 PCM traffic and load the selected MWK.
- No parser, page CRC, engine runtime or MoonSound errors occurred.
- The KSP remains KSP 1.04 and is 542 KiB.

The remaining fidelity risk is instrument/sample substitution. If a background
part is still absent after these pitch and timing corrections, its bank mapping
or YRW801/custom-sample choice must be compared with the source SBNK/SWAR data.
