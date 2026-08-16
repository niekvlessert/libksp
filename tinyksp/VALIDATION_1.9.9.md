# TinyKSP 1.9.9 KSS/compare validation

Validation performed on Linux x86-64 against the 1.9.8 D84F-fixed project tree.

## Passed

- Release build completes with bundled libvgm.
- `tinyksp -v` reports 1.9.9.
- Existing KSP direct-VM dry run still passes on the synthetic SCC+PSG fixture.
- New `kss_vm_smoke` passes: KSSX parse, INIT, 60 Hz PLAY scheduling, PSG output,
  trace capture and non-silent PCM.
- Existing `z80_smoke` passes.
- Synthetic equivalent KSP/KSS pair, one second:
  - 59 PLAY calls on both sides;
  - 63 canonical chip writes on both sides;
  - canonical trace identical;
  - stereo PCM bit-identical;
  - comparator exits 0.
- Synthetic mismatch (PSG register 8 changed from 0Fh to 0Eh):
  - comparator reports first divergence as INIT / PSG register 8;
  - reports first differing PCM frame, timestamp and channel;
  - reports differing sample count and maximum delta;
  - exits 3.
- KSSX first-song ID 1 test maps user-facing `--track 1` to KSS song 1 and
  remains bit-identical to the matching KSP.

## Baseline note

The historical `yamaha_smoke` OPL4 PCM test currently reports
`OPL4 PCM did not produce audio` in this Linux environment. The unmodified
1.9.8 D84F-fixed baseline produces the same failure, so this is not introduced
by the KSS/compare changes. No YMF278B playback code was changed in 1.9.9.
