# Fray page-1 KSP rebuild requirements

## Diagnosis

`FRAY_KSP1_PAGE1_SAFE.ksp` is not fully relocated. Its KSP tables and stored
CRCs are internally consistent, but the executable image still contains live
absolute references to the original `C000h-FFFFh` driver image. On MSX-DOS2
those references access page 3 instead of Fray-owned RAM. Page-3 contents vary
with DOS, interrupts, and player activity, which produces nondeterministic
missing/wrong notes and can corrupt or crash DOS.

Examples found in executable routines include references to `D80Dh-D819h`,
`D847h`, `DAA0h`, and `CF2Dh`. Correcting only `D847h` and `D80Eh` does not fix
the pack; many more old operands remain.

Passing the KSP page CRC checks does not prove that the relocation is correct.
Those CRCs were calculated from the already incorrectly relocated pages.

## Required rebuild

Relocate the original Fray runtime image as one symbol-aware operation:

```text
original runtime: C000h-FFFFh
new runtime:      4000h-7FFFh
relocation delta: -8000h
new INIT:         4CABh (or a documented replacement wrapper)
new PLAY:         4E00h
```

For every common-template and track-specific runtime page:

1. Relocate every instruction operand whose target is a code or data symbol in
   the original `C000h-FFFFh` image.
2. Relocate every pointer stored in tables, jump tables, callback tables, and
   self-modifying-code operands when it names that image.
3. Relocate track-overlay destinations from `C000h-FFFFh` to `4000h-7FFFh`.
4. Apply the same relocation to address-bearing bytes supplied by overlays,
   not only to the common template.
5. Do not relocate external addresses merely because their numeric value is
   high. Page-2 banks, BIOS/work-area references, hardware windows, ports, and
   constants require explicit classification.
6. Remove the old `2000h` mapper/bank-selection stub, or replace it with a
   page-1 INIT wrapper whose complete behavior is documented.
7. Ensure all mutable Fray state is inside player-owned page-1 RAM. No normal
   INIT or PLAY path may read or write DOS2 page 3.
8. Change the relocated PLAY dispatcher's `EI; RET` to `DI; RET`, or otherwise
   guarantee that PLAY cannot enable an interrupt before returning to the
   player. The player owns VBlank scheduling.
9. Rebuild the KSP template and sparse overlays, then recompute template, page,
   index, and header CRCs.

Do not implement relocation by scanning arbitrary bytes for values in
`C000h-FFFFh`. Music and table data can contain coincidental byte pairs. Use
driver source/linker relocation information or a reviewed relocation table.

## Mandatory validation

The rebuilt pack is acceptable only when all of these checks pass:

- Disassemble every reachable INIT and PLAY path for every reconstructed page.
- No operand or image-owned pointer still targets the old `C000h-FFFFh` image.
- Every relocated page is compared with the corresponding original page using
  the reviewed relocation map; do not validate only against newly stored CRCs.
- INIT starts from a defined state and clears all driver variables required by
  the first PLAY call.
- The same track can be started repeatedly after a fresh player launch and
  after several track changes with byte-identical FM/PSG register traces.
- Track changes, wraparound, and Escape do not modify DOS2 page 3 outside the
  DOS/player's expected writes.
- KSP header, template, page, index, and resource CRC checks all pass.

The strongest regression test is deterministic hardware output: record all
YM2413 and PSG writes for the first several seconds of a track, repeat the same
start sequence at least three times, and require identical traces.
