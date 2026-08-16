# v0.1.0 validation

Baseline tested: 268 KSP outputs from supplied `HOOT_KSS2KSP_NATIVE_v0.10.0_complete_package.zip`.

## Fast structural audit

- Parsed: 268/268
- Strict `$4000/$4000`: 51
- `LIKELY SAFE` structural candidates: 51
- Structural `BLOCKER`: 217

This is a structural prefilter only. The 51 candidates still require the normal deep pass and runtime validation.

## Targeted deep checks

- `Ys 2`: old v0.10 hosted `$0000/$C000 + PAGE2_RUNTIME` is identified as a blocker; runtime mirror would extend to `$13FFF`.
- `OutRun`: old nearly-full-address-space image is immediately identified as non-native geometry.
- `Hyper Sports 2`: page geometry is native, but deep analysis identifies the old SCC declaration as suspicious/high-risk because `$9800` is PAGE2 RAM and no SCC slot ABI call proves an SCC window.
- `Rice 1`: KSP `$D900/$D908` SCC ABI tokens are recognized and not falsely reported as missing page-3 code; remaining unresolved indirect jumps are reported as `SUSPICIOUS`, not a blocker.

The historical v0.10 corpus is intentionally not treated as the final strict-native release set.


# v0.1.3 validation

## Q-Bert repair/output regression

Input: `Q-Bert (MSX)(1986)(Konami).ksp`.

Original deep result:

- `BLOCKER`: INIT can return with interrupts enabled;
- `HIGH`: PLAY can return with interrupts enabled;
- declared hardware: PSG + SCC;
- statically proven chip I/O: PSG only.

`--build-disk` candidate result:

- causal `$4C58: EI -> DI` repair applied;
- emitted engine hardware mask: `0x00000001` (PSG only);
- META `target_hardware=PSG`;
- META `source_hardware=SCC + PSG` preserved;
- header CRC: valid;
- index CRC: valid;
- materialized byte at `$4C58`: `$F3` (`DI`);
- emitted KSP deep verdict: `LIKELY SAFE`.

The active build environment did not contain `KSP1PLAY_v0.47.1_BASE.DSK`, so a
real v0.47.1 test DSK could not be emitted during this release build. This is an
intentional hard stop: an available v0.22.24 DSK was explicitly tested as a
negative case and rejected rather than being used as a silent fallback.
